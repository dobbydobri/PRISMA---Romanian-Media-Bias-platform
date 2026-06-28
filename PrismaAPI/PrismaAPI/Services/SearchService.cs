using System.Net.Http.Json;
using Microsoft.Extensions.Options;
using Npgsql;
using Pgvector;
using PrismaAPI.Configuration;
using PrismaAPI.DTOs.Search;

namespace PrismaAPI.Services;

public class SearchService : ISearchService
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly NpgsqlDataSource _dataSource;
    private readonly IOptions<SearchOptions> _options;
    private readonly ILogger<SearchService> _logger;

    public SearchService(
        IHttpClientFactory httpClientFactory,
        NpgsqlDataSource dataSource,
        IOptions<SearchOptions> options,
        ILogger<SearchService> logger)
    {
        _httpClientFactory = httpClientFactory;
        _dataSource = dataSource;
        _options = options;
        _logger = logger;
    }

    public async Task<SearchResponse> SearchArticlesAsync(SearchRequest request, CancellationToken ct)
    {
        var opts = _options.Value;
        var query = request.Query.Trim();

        _logger.LogInformation(
            "Hybrid search: query={Query}, top_k={TopK}, filters={Filters}",
            query, request.TopK, request.Filters != null);

        float[] queryVector = await EmbedQueryAsync(query, ct);

        var articles = await ExecuteHybridSearchAsync(queryVector, query, request, ct);

        int topK = Math.Clamp(request.TopK ?? opts.DefaultTopK, 1, opts.MaxTopK);
        return BuildResponse(query, articles, opts, topK);
    }


    private async Task<float[]> EmbedQueryAsync(string text, CancellationToken ct)
    {
        var client = _httpClientFactory.CreateClient("QueryEmbedder");

        _logger.LogDebug("Calling embedder at {BaseAddress}/embed_query", client.BaseAddress);

        var payload = new { text };
        var response = await client.PostAsJsonAsync("/embed_query", payload, ct);

        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            _logger.LogError(
                "Embedder returned {StatusCode}: {Body}", response.StatusCode, body);
            throw new HttpRequestException(
                $"Embedder returned {(int)response.StatusCode}: {body}");
        }

        var result = await response.Content.ReadFromJsonAsync<EmbedResponse>(
            cancellationToken: ct);

        if (result?.Embedding is null || result.Embedding.Length != 1024)
        {
            _logger.LogError(
                "Embedder returned invalid vector: length={Length}",
                result?.Embedding?.Length ?? 0);
            throw new InvalidOperationException(
                "Embedder returned invalid response: expected 1024-dimensional vector.");
        }

        return result.Embedding;
    }

    private sealed record EmbedResponse(float[] Embedding, int Dim, double EncodeMs);


    private async Task<List<ArticleSearchResult>> ExecuteHybridSearchAsync(
        float[] queryVector,
        string queryText,
        SearchRequest request,
        CancellationToken ct)
    {
        var opts = _options.Value;

        var (filterSql, filterParams) = BuildFilterClauses(request.Filters);

        string sql = $"""
            WITH
            query AS (
                SELECT
                    @qvec::vector(1024)                              AS qvec,
                    websearch_to_tsquery('romanian', @qtext)         AS qts
            ),
            dense_topk AS (
                SELECT a.id,
                       1 - (a.embedding <=> q.qvec) AS cos_sim
                FROM   articles a, query q
                WHERE  a.embedding IS NOT NULL
                  AND  NOT a.is_templated
                  AND  NOT a.is_excluded
                  AND  a.fts @@ q.qts          -- title OR body must match lexically
                  {filterSql}
                ORDER  BY a.embedding <=> q.qvec
                LIMIT  @candidates
            ),
            dense AS (
                SELECT id,
                       cos_sim,
                       ROW_NUMBER() OVER (ORDER BY cos_sim DESC) AS rnk
                FROM   dense_topk
                WHERE  cos_sim >= @cos_sim_floor
            ),
            sparse AS (
                SELECT a.id,
                       ts_rank_cd(a.fts, q.qts, 4) AS ts_score,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank_cd(a.fts, q.qts, 4) DESC
                       ) AS rnk
                FROM   articles a, query q
                WHERE  a.fts @@ q.qts
                  AND  NOT a.is_templated
                  AND  NOT a.is_excluded
                  {filterSql}
                ORDER  BY ts_rank_cd(a.fts, q.qts, 4) DESC
                LIMIT  @candidates
            ),
            fused AS (
                SELECT COALESCE(d.id, s.id)                     AS id,
                       COALESCE(1.0 / (@rrf_k + d.rnk), 0)
                     + COALESCE(1.0 / (@rrf_k + s.rnk), 0)     AS rrf_score,
                       d.rnk     AS dense_rank,
                       s.rnk     AS sparse_rank,
                       d.cos_sim,
                       s.ts_score
                FROM   dense d
                FULL OUTER JOIN sparse s USING (id)
            )
            SELECT f.id,
                   a.title,
                   a.url,
                   a.outlet_id,
                   o.name                              AS outlet_name,
                   a.published_at,
                   f.dense_rank,
                   f.sparse_rank,
                   f.cos_sim,
                   f.ts_score,
                   f.rrf_score,
                   a.cluster_id,
                   a.sub_cluster_id,
                   a.score_sensationalism,
                   a.score_citation_quality,
                   a.score_rhetoric_intensity
            FROM   fused f
            JOIN   articles a ON a.id = f.id
            JOIN   outlets  o ON o.id = a.outlet_id
            ORDER  BY f.rrf_score DESC
            LIMIT  @pool_size;
            """;

        await using var conn = await _dataSource.OpenConnectionAsync(ct);

        await using (var setCmd = new NpgsqlCommand(
            $"SET hnsw.ef_search = {opts.HnswEfSearch};", conn))
        {
            await setCmd.ExecuteNonQueryAsync(ct);
        }

        await using var cmd = new NpgsqlCommand(sql, conn);

        cmd.Parameters.AddWithValue("@qvec", new Vector(queryVector));
        cmd.Parameters.AddWithValue("@qtext", queryText);
        cmd.Parameters.AddWithValue("@candidates", opts.CandidatesPerLeg);
        cmd.Parameters.AddWithValue("@rrf_k", opts.RrfK);
        cmd.Parameters.AddWithValue("@cos_sim_floor", opts.CosSimFloor);
        cmd.Parameters.AddWithValue("@pool_size", opts.CandidatesPerLeg);

        foreach (var (name, value) in filterParams)
            cmd.Parameters.AddWithValue(name, value);

        await using var reader = await cmd.ExecuteReaderAsync(ct);

        var results = new List<ArticleSearchResult>();

        while (await reader.ReadAsync(ct))
        {
            results.Add(new ArticleSearchResult
            {
                Id                     = reader.GetInt64(0),
                Title                  = reader.GetString(1),
                Url                    = reader.IsDBNull(2)  ? null : reader.GetString(2),
                OutletId               = reader.GetInt32(3),
                OutletName             = reader.GetString(4),
                PublishedAt            = reader.IsDBNull(5)  ? null : reader.GetDateTime(5),
                DenseRank              = reader.IsDBNull(6)  ? null : reader.GetInt64(6),
                SparseRank             = reader.IsDBNull(7)  ? null : reader.GetInt64(7),
                CosSim                 = reader.IsDBNull(8)  ? null : reader.GetDouble(8),
                TsScore                = reader.IsDBNull(9)  ? null : reader.GetDouble(9),
                RrfScore               = reader.GetDouble(10),
                ClusterId              = reader.IsDBNull(11) ? null : reader.GetInt32(11),
                SubClusterId           = reader.IsDBNull(12) ? null : reader.GetInt32(12),
                ScoreSensationalism    = reader.IsDBNull(13) ? null : reader.GetDouble(13),
                ScoreCitationQuality   = reader.IsDBNull(14) ? null : reader.GetDouble(14),
                ScoreRhetoricIntensity = reader.IsDBNull(15) ? null : reader.GetDouble(15),
            });
        }

        return results;
    }


    private static (string sql, List<(string name, object value)> parameters)
        BuildFilterClauses(SearchFilters? filters)
    {
        if (filters is null)
            return ("", new());

        var clauses = new List<string>();
        var parameters = new List<(string, object)>();

        if (filters.OutletIds is { Length: > 0 })
        {
            clauses.Add("AND a.outlet_id = ANY(@outlet_ids)");
            parameters.Add(("@outlet_ids", filters.OutletIds));
        }

        if (filters.DateFrom.HasValue)
        {
            clauses.Add("AND a.published_at >= @date_from");
            parameters.Add(("@date_from", filters.DateFrom.Value.ToDateTime(TimeOnly.MinValue)));
        }

        if (filters.DateTo.HasValue)
        {
            clauses.Add("AND a.published_at <= @date_to");
            parameters.Add(("@date_to", filters.DateTo.Value.ToDateTime(TimeOnly.MaxValue)));
        }

        if (filters.IsFactCheck.HasValue)
        {
            if (filters.IsFactCheck.Value)
                clauses.Add("AND a.outlet_id IN (SELECT id FROM outlets WHERE outlet_type = 'fact_checker')");
            else
                clauses.Add("AND a.outlet_id NOT IN (SELECT id FROM outlets WHERE outlet_type = 'fact_checker')");
        }

        if (!string.IsNullOrWhiteSpace(filters.Topic))
        {
            clauses.Add("AND a.llm_topic = @topic");
            parameters.Add(("@topic", filters.Topic));
        }

        return (string.Join("\n                  ", clauses), parameters);
    }


    private static SearchResponse BuildResponse(
        string query,
        List<ArticleSearchResult> articles,
        SearchOptions opts,
        int topK)
    {
        if (articles.Count > 3)
        {
            double baselineScore = articles[2].RrfScore;
            double floor = baselineScore * opts.ScoreRetainRatio;
            
            var top3 = articles.Take(3);
            var tail = articles.Skip(3).TakeWhile(a => a.RrfScore >= floor);
            articles = top3.Concat(tail).ToList();
        }

        if (articles.Count > topK)
        {
            articles = articles.Take(topK).ToList();
        }

        int agreementCount = articles.Count(a => a.DenseRank.HasValue && a.SparseRank.HasValue);

        double topRrfScore = articles.Count > 0 ? articles[0].RrfScore : 0.0;
        double? topCosSim  = articles.Count > 0 ? articles[0].CosSim   : null;

        string tier;
        if (topRrfScore >= 0.025 && agreementCount >= 3)
            tier = "HIGH";
        else if (topRrfScore >= 0.020 || agreementCount >= 1)
            tier = "MEDIUM";
        else
            tier = "LOW";

        return new SearchResponse
        {
            Query       = query,
            ResultCount = articles.Count,
            Confidence  = new SearchConfidence
            {
                Tier           = tier,
                TopRrfScore    = topRrfScore,
                TopCosSim      = topCosSim,
                AgreementCount = agreementCount,
            },
            Articles = articles,
        };
    }
}
