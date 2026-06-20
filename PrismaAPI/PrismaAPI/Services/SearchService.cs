using System.Net.Http.Json;
using Microsoft.Extensions.Options;
using Npgsql;
using PrismaAPI.Configuration;
using PrismaAPI.DTOs.Search;
using PrismaAPI.Extensions;

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

        return BuildResponse(query, articles);
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
        int topK = Math.Clamp(request.TopK ?? opts.DefaultTopK, 1, opts.MaxTopK);

        var (filterSql, filterParams) = BuildFilterClauses(request.Filters);

        // (like `NOT is_templated`) remove a large fraction of the index neighborhood.
        //
        string sql = $"""
            WITH
            params AS (
                SELECT
                    @qvec::vector(1024)                              AS qvec,
                    websearch_to_tsquery('romanian', @qtext)         AS qts,
                    @candidates                                      AS candidates,
                    @rrf_k                                           AS rrf_k,
                    @cos_sim_floor                                   AS cos_sim_floor
            ),
            dense_topk AS (
                SELECT a.id,
                       1 - (a.embedding <=> p.qvec)  AS cos_sim,
                       a.embedding <=> p.qvec         AS dist
                FROM   articles a, params p
                WHERE  a.embedding IS NOT NULL
                  AND  NOT a.is_templated
                  {filterSql}
                ORDER  BY a.embedding <=> p.qvec
                LIMIT  @candidates
            ),
            dense AS (
                SELECT id,
                       cos_sim,
                       ROW_NUMBER() OVER (ORDER BY cos_sim DESC) AS rnk
                FROM   dense_topk, params
                WHERE  cos_sim >= cos_sim_floor
            ),
            sparse AS (
                SELECT a.id,
                       ts_rank_cd(a.fts, p.qts) AS ts_score,
                       ROW_NUMBER() OVER (ORDER BY ts_rank_cd(a.fts, p.qts) DESC) AS rnk
                FROM   articles a, params p
                WHERE  a.fts @@ p.qts
                  AND  NOT a.is_templated
                  {filterSql}
                ORDER  BY ts_rank_cd(a.fts, p.qts) DESC
                LIMIT  @candidates
            ),
            fused AS (
                SELECT COALESCE(d.id, s.id)                                         AS id,
                       COALESCE(1.0 / ((SELECT rrf_k FROM params) + d.rnk), 0)
                     + COALESCE(1.0 / ((SELECT rrf_k FROM params) + s.rnk), 0)     AS rrf_score,
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
            LIMIT  @top_k;
            """;

        await using var conn = await _dataSource.OpenConnectionAsync(ct);

        await using (var setCmd = new NpgsqlCommand(
            $"SET hnsw.ef_search = {opts.HnswEfSearch};", conn))
        {
            await setCmd.ExecuteNonQueryAsync(ct);
        }

        await using var cmd = new NpgsqlCommand(sql, conn);

        cmd.Parameters.AddWithValue("@qvec", queryVector.ToVectorString());
        cmd.Parameters.AddWithValue("@qtext", queryText);
        cmd.Parameters.AddWithValue("@candidates", opts.CandidatesPerLeg);
        cmd.Parameters.AddWithValue("@rrf_k", opts.RrfK);
        cmd.Parameters.AddWithValue("@cos_sim_floor", opts.CosSimFloor);
        cmd.Parameters.AddWithValue("@top_k", topK);

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
                clauses.Add("AND a.outlet_id IN (3, 6)");
            else
                clauses.Add("AND a.outlet_id NOT IN (3, 6)");
        }

        return (string.Join("\n                  ", clauses), parameters);
    }


    private static SearchResponse BuildResponse(string query, List<ArticleSearchResult> articles)
    {
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
