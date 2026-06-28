using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using Dapper;
using Npgsql;
using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public class ConnectionsPathService : IConnectionsPathService
{
    private readonly NpgsqlDataSource _dataSource;
    private readonly HttpClient _graphServiceClient;
    private readonly ILogger<ConnectionsPathService> _logger;

    private const int MaxDirectArticles = 20;
    private const int MaxEdgeArticles = 10;

    public ConnectionsPathService(
        NpgsqlDataSource dataSource,
        IHttpClientFactory httpClientFactory,
        ILogger<ConnectionsPathService> logger)
    {
        _dataSource = dataSource;
        _graphServiceClient = httpClientFactory.CreateClient("GraphService");
        _logger = logger;
    }

    // ── Autocomplete ──────────────────────────────────────────────────────────

    public async Task<List<EntitySuggestionDto>> AutocompleteAsync(string query, int limit = 20)
    {
        if (string.IsNullOrWhiteSpace(query) || query.Length < 2)
            return [];

        const string sql = """
            SELECT canonical_name, label, article_count, node_degree
            FROM entity_directory
            WHERE canonical_name % @Query
               OR canonical_name ILIKE @Prefix
            ORDER BY
                (canonical_name ILIKE @Prefix)::int DESC,
                node_degree DESC,
                article_count DESC
            LIMIT @Limit;
            """;

        await using var conn = await _dataSource.OpenConnectionAsync();
        var rows = await conn.QueryAsync(sql, new
        {
            Query = query,
            Prefix = $"{query}%",
            Limit = limit
        });

        return rows.Select(r => new EntitySuggestionDto(
            (string)r.canonical_name,
            (string)r.label,
            (int)r.article_count,
            (int)r.node_degree
        )).ToList();
    }

    // ── Main path-finding ─────────────────────────────────────────────────────

    public async Task<EntityPathResponseDto?> FindPathAsync(string entityA, string entityB)
    {
        // 1. Fetch direct connection articles
        var directTask = GetDirectArticlesAsync(entityA, entityB);

        // 2. Call graph service for indirect paths
        var indirectTask = GetIndirectPathsAsync(entityA, entityB);

        await Task.WhenAll(directTask, indirectTask);

        var directArticles = await directTask;
        var rawPaths = await indirectTask;

        // Build DirectConnectionDto
        DirectConnectionDto? direct = null;
        if (directArticles.Count > 0)
        {
            direct = new DirectConnectionDto(
                ArticleCount: directArticles.Count,
                Articles: directArticles.Take(MaxDirectArticles).ToList()
            );
        }

        // Enrich indirect paths with supporting articles per edge
        var indirect = new List<IndirectPathDto>();
        foreach (var rawPath in rawPaths)
        {
            var enrichedEdges = new List<PathEdgeDto>();
            foreach (var edge in rawPath.Edges)
            {
                var edgeArticles = await GetEdgeArticlesAsync(edge.From, edge.To);
                enrichedEdges.Add(edge with { Articles = edgeArticles });
            }
            indirect.Add(rawPath with { Edges = enrichedEdges });
        }

        // Return null only if both direct and indirect are empty
        if (direct is null && indirect.Count == 0)
            return null;

        return new EntityPathResponseDto(
            EntityA: entityA,
            EntityB: entityB,
            Direct: direct,
            Indirect: indirect
        );
    }

    // ── Direct connection articles ─────────────────────────────────────────────

    private async Task<List<ConnectionArticleDto>> GetDirectArticlesAsync(
        string entityA, string entityB)
    {
        const string sql = """
            SELECT
                a.id,
                a.title,
                a.url,
                o.name AS outlet,
                a.published_at
            FROM articles a
            JOIN outlets o ON o.id = a.outlet_id
            WHERE a.id IN (
                SELECT ae1.article_id
                FROM article_entities_full ae1
                JOIN article_entities_full ae2 ON ae2.article_id = ae1.article_id
                WHERE ae1.entity_text = @EntityA
                  AND ae2.entity_text = @EntityB
            )
            AND (a.is_excluded = false OR a.is_excluded IS NULL)
            ORDER BY a.published_at DESC
            LIMIT @Limit;
            """;

        await using var conn = await _dataSource.OpenConnectionAsync();
        var rows = await conn.QueryAsync(sql, new
        {
            EntityA = entityA,
            EntityB = entityB,
            Limit = MaxDirectArticles
        });

        return rows.Select(MapArticle).ToList();
    }

    // ── Edge supporting articles ───────────────────────────────────────────────

    private async Task<List<ConnectionArticleDto>> GetEdgeArticlesAsync(
        string entityFrom, string entityTo)
    {
        // Get articles supporting a single edge, ranked by recency.
        // One article per outlet (outlet diversity), then top-up with recency.
        const string sql = """
            WITH edge_articles AS (
                SELECT
                    a.id,
                    a.title,
                    a.url,
                    o.name AS outlet,
                    a.published_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY o.id ORDER BY a.published_at DESC
                    ) AS rn_per_outlet
                FROM articles a
                JOIN outlets o ON o.id = a.outlet_id
                WHERE a.id IN (
                    SELECT ae1.article_id
                    FROM article_entities_full ae1
                    JOIN article_entities_full ae2 ON ae2.article_id = ae1.article_id
                    WHERE ae1.entity_text = @EntityFrom
                      AND ae2.entity_text = @EntityTo
                )
                AND (a.is_excluded = false OR a.is_excluded IS NULL)
            )
            SELECT id, title, url, outlet, published_at
            FROM edge_articles
            WHERE rn_per_outlet = 1
            ORDER BY published_at DESC
            LIMIT @Limit;
            """;

        await using var conn = await _dataSource.OpenConnectionAsync();
        var rows = await conn.QueryAsync(sql, new
        {
            EntityFrom = entityFrom,
            EntityTo = entityTo,
            Limit = MaxEdgeArticles
        });

        return rows.Select(MapArticle).ToList();
    }

    // ── Graph service call ─────────────────────────────────────────────────────

    private async Task<List<IndirectPathDto>> GetIndirectPathsAsync(
        string entityA, string entityB)
    {
        try
        {
            var response = await _graphServiceClient.PostAsJsonAsync("/paths", new
            {
                a = entityA,
                b = entityB,
                k = 5,
                max_hops = 3
            });

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning(
                    "Graph service returned {Status} for {A}→{B}",
                    response.StatusCode, entityA, entityB);
                return [];
            }

            var result = await response.Content.ReadFromJsonAsync<GraphServicePathResponse>();
            if (result?.Paths is null || result.Paths.Count == 0)
                return [];

            return result.Paths
                .Where(p => p.Hops >= 2)  // indirect only — length 1 handled by direct query
                .Select(p => new IndirectPathDto(
                    Nodes: p.Nodes,
                    Score: p.Score,
                    Hops: p.Hops,
                    Edges: p.Edges.Select(e => new PathEdgeDto(
                        From: e.From,
                        To: e.To,
                        Pmi: e.Pmi,
                        Raw: e.Raw,
                        Articles: []  // populated in FindPathAsync
                    )).ToList()
                ))
                .ToList();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Graph service call failed for {A}→{B}", entityA, entityB);
            return [];
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static ConnectionArticleDto MapArticle(dynamic r) => new(
        Id: (long)r.id,
        Title: (string)(r.title ?? ""),
        Url: (string)(r.url ?? ""),
        Outlet: (string)(r.outlet ?? ""),
        PublishedAt: r.published_at is DateTime dt
            ? new DateTimeOffset(dt, TimeSpan.Zero)
            : (DateTimeOffset?)null
    );

    // Internal response shape from graph service
    private record GraphServicePathResponse(
        [property: JsonPropertyName("paths")] List<GraphServicePath> Paths,
        [property: JsonPropertyName("found")] bool Found
    );

    private record GraphServicePath(
        [property: JsonPropertyName("nodes")] List<string> Nodes,
        [property: JsonPropertyName("score")] double Score,
        [property: JsonPropertyName("hops")] int Hops,
        [property: JsonPropertyName("edges")] List<GraphServiceEdge> Edges
    );

    private record GraphServiceEdge(
        [property: JsonPropertyName("from")] string From,
        [property: JsonPropertyName("to")] string To,
        [property: JsonPropertyName("pmi")] double Pmi,
        [property: JsonPropertyName("raw")] int Raw
    );
}
