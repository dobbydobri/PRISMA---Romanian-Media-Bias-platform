using Microsoft.EntityFrameworkCore;
using Npgsql;
using NpgsqlTypes;
using Pgvector;
using PrismaAPI.Data;
using PrismaAPI.DTOs;
using PrismaAPI.DTOs.FactCheck;
using PrismaAPI.Models;

namespace PrismaAPI.Services;

public class FactCheckService
{
    private readonly PrismaDbContext _context;
    private readonly ILogger<FactCheckService> _logger;

    public FactCheckService(PrismaDbContext context, ILogger<FactCheckService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<PaginatedResultDto<FactCheckDto>> GetAllAsync(
        string? verdict, string? verdictType, int page = 1, int pageSize = 20)
    {
        _logger.LogInformation(
            "Fetching fact checks: verdict={Verdict}, verdictType={VerdictType}, page={Page}, pageSize={PageSize}",
            verdict, verdictType, page, pageSize);

        pageSize = Math.Clamp(pageSize, 1, 100);
        page = Math.Max(1, page);

        var query = _context.FactChecks.AsNoTracking().AsQueryable();

        if (!string.IsNullOrWhiteSpace(verdict))
            query = query.Where(fc => fc.Verdict == verdict);

        if (!string.IsNullOrWhiteSpace(verdictType))
            query = query.Where(fc => fc.VerdictType == verdictType);

        var totalCount = await query.CountAsync();

        var items = await query
            .OrderByDescending(fc => fc.PublishedAt)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Join(_context.Articles.AsNoTracking(),
                fc => fc.ArticleId, a => a.Id,
                (fc, a) => new { fc, a })
            .Join(_context.Outlets.AsNoTracking(),
                x => x.fc.OutletId, o => o.Id,
                (x, o) => new { x.fc, x.a, o })
            .GroupJoin(
                _context.ClusterLabels.AsNoTracking(),
                x => new { ClusterRunId = x.a.ClusterRunId ?? 0, ClusterId = x.a.ClusterId ?? 0 },
                cl => new { cl.ClusterRunId, cl.ClusterId },
                (x, cls) => new { x.fc, x.a, x.o, cls })
            .SelectMany(
                x => x.cls.DefaultIfEmpty(),
                (x, cl) => new FactCheckDto
                {
                    Id = x.fc.Id,
                    ArticleId = x.fc.ArticleId,
                    ArticleTitle = x.a.Title,
                    OutletName = x.o.Name,
                    Verdict = x.fc.Verdict,
                    VerdictType = x.fc.VerdictType,
                    ClaimText = x.fc.ClaimText,
                    RawVerdict = x.fc.RawVerdict,
                    PublishedAt = x.fc.PublishedAt,
                    LinkedClusterId = x.a.ClusterId,
                    LinkedClusterLabel = cl != null ? cl.LabelText : null
                })
            .ToListAsync();

        return new PaginatedResultDto<FactCheckDto>
        {
            Items = items,
            TotalCount = totalCount,
            Page = page,
            PageSize = pageSize
        };
    }

    public async Task<List<FactCheckClusterDto>> GetByClusterAsync(int runId, int clusterId)
    {
        _logger.LogInformation(
            "Fetching Tier 1 fact checks for cluster run={RunId}, cluster={ClusterId}", runId, clusterId);

        return await _context.FactCheckClusterMaps
            .AsNoTracking()
            .Where(m => m.ClusterRunId == runId && m.ClusterId == clusterId)
            .Join(_context.FactChecks.AsNoTracking(),
                m => m.FactcheckId, fc => fc.Id,
                (m, fc) => new { m, fc })
            .Join(_context.Articles.AsNoTracking(),
                x => x.fc.ArticleId, a => a.Id,
                (x, a) => new { x.m, x.fc, a })
            .Join(_context.Outlets.AsNoTracking(),
                x => x.fc.OutletId, o => o.Id,
                (x, o) => new FactCheckClusterDto
                {
                    FactcheckId = x.m.FactcheckId,
                    ArticleId = x.fc.ArticleId,
                    ArticleTitle = x.a.Title,
                    OutletName = o.Name,
                    Verdict = x.fc.Verdict,
                    VerdictType = x.fc.VerdictType,
                    ClaimText = x.fc.ClaimText,
                    ClusterRunId = x.m.ClusterRunId,
                    ClusterId = x.m.ClusterId,
                    SubClusterId = x.m.SubClusterId,
                    Similarity = x.m.Similarity,
                    SubSimilarity = x.m.SubSimilarity
                })
            .OrderByDescending(x => x.Similarity)
            .ToListAsync();
    }

    public async Task<List<FactCheckProximityDto>> GetProximityAsync(
        long articleId, double threshold = 0.7, int limit = 10)
    {
        _logger.LogInformation(
            "Fetching Tier 2 proximity fact checks for article={ArticleId}, threshold={Threshold}, limit={Limit}",
            articleId, threshold, limit);

        limit = Math.Clamp(limit, 1, 100);

        var sourceArticle = await _context.Articles
            .AsNoTracking()
            .Where(a => a.Id == articleId)
            .Select(a => new { a.Embedding })
            .FirstOrDefaultAsync();

        if (sourceArticle?.Embedding == null)
        {
            _logger.LogWarning("Article {ArticleId} not found or has no embedding", articleId);
            return new List<FactCheckProximityDto>();
        }

        var embeddingString = $"[{string.Join(",", sourceArticle.Embedding.ToArray())}]";

        var sql = @"
            SELECT fc.id AS ""FactCheckId"", fc.article_id AS ""ArticleId"",
                   a.title AS ""FactCheckArticleTitle"", a.url AS ""FactCheckArticleUrl"",
                   o.name AS ""OutletName"", fc.verdict AS ""Verdict"",
                   fc.claim_text AS ""ClaimText"",
                   (a.embedding <=> @sourceEmbedding::vector) AS ""Distance""
            FROM fact_checks fc
            JOIN articles a ON fc.article_id = a.id
            JOIN outlets o ON fc.outlet_id = o.id
            WHERE a.embedding IS NOT NULL
              AND a.id != @articleId
              AND (a.embedding <=> @sourceEmbedding::vector) < @threshold
            ORDER BY ""Distance""
            LIMIT @limit";

        var results = await _context.Database
            .SqlQueryRaw<FactCheckProximityDto>(
                sql,
                new NpgsqlParameter("@sourceEmbedding", embeddingString),
                new NpgsqlParameter("@articleId", articleId),
                new NpgsqlParameter("@threshold", threshold),
                new NpgsqlParameter("@limit", limit))
            .ToListAsync();

        return results;
    }

    public async Task<List<FactCheckDto>> GetByArticleAsync(long articleId)
    {
        _logger.LogInformation("Fetching all fact checks for article {ArticleId}", articleId);

        var results = new List<FactCheckDto>();

        var article = await _context.Articles
            .AsNoTracking()
            .Where(a => a.Id == articleId)
            .Select(a => new { a.ClusterRunId, a.ClusterId })
            .FirstOrDefaultAsync();

        if (article?.ClusterRunId != null && article.ClusterId != null)
        {
            var tier1 = await _context.FactCheckClusterMaps
                .AsNoTracking()
                .Where(m => m.ClusterRunId == article.ClusterRunId
                         && m.ClusterId == article.ClusterId)
                .Join(_context.FactChecks.AsNoTracking(),
                    m => m.FactcheckId, fc => fc.Id,
                    (m, fc) => new { m, fc })
                .Join(_context.Articles.AsNoTracking(),
                    x => x.fc.ArticleId, a => a.Id,
                    (x, a) => new { x.m, x.fc, a })
                .Join(_context.Outlets.AsNoTracking(),
                    x => x.fc.OutletId, o => o.Id,
                    (x, o) => new FactCheckDto
                    {
                        Id = x.fc.Id,
                        ArticleId = x.fc.ArticleId,
                        ArticleTitle = x.a.Title,
                        OutletName = o.Name,
                        Verdict = x.fc.Verdict,
                        VerdictType = x.fc.VerdictType,
                        ClaimText = x.fc.ClaimText,
                        RawVerdict = x.fc.RawVerdict,
                        PublishedAt = x.fc.PublishedAt
                    })
                .ToListAsync();

            results.AddRange(tier1);
        }

        try
        {
            var proximityResults = await GetProximityAsync(articleId, threshold: 0.5, limit: 10);
            var proximityDtos = proximityResults.Select(p => new FactCheckDto
            {
                Id = p.FactCheckId,
                ArticleId = p.ArticleId,
                ArticleTitle = p.FactCheckArticleTitle,
                OutletName = p.OutletName,
                Verdict = p.Verdict,
                ClaimText = p.ClaimText
            });

            var existingIds = results.Select(r => r.Id).ToHashSet();
            results.AddRange(proximityDtos.Where(p => !existingIds.Contains(p.Id)));
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex,
                "Failed to fetch proximity fact checks for article {ArticleId}", articleId);
        }

        return results;
    }

    public async Task<PaginatedResultDto<FactCheckListItemDto>> GetListAsync(
        int page,
        int pageSize,
        string? verdict,
        CancellationToken ct)
    {
        _logger.LogInformation(
            "Fetching fact-check explore list: verdict={Verdict}, page={Page}, pageSize={PageSize}",
            verdict, page, pageSize);

        var verdictValue = (object?)verdict ?? DBNull.Value;

        var countSql = @"
            SELECT COUNT(*)::integer AS ""Value""
            FROM fact_checks fc
            JOIN articles a ON a.id = fc.article_id
            JOIN outlets o  ON o.id = a.outlet_id
            WHERE o.outlet_type = 'fact_checker'
              AND (@verdict IS NULL OR fc.verdict = @verdict)";

        var totalCount = await _context.Database
            .SqlQueryRaw<int>(
                countSql,
                new NpgsqlParameter("@verdict", NpgsqlDbType.Varchar) { Value = verdictValue })
            .FirstOrDefaultAsync(ct);

        var dataSql = @"
            SELECT
                fc.id                                AS ""Id"",
                fc.article_id                        AS ""ArticleId"",
                a.title                              AS ""Title"",
                o.name                               AS ""OutletName"",
                fc.verdict                           AS ""Verdict"",
                fc.verdict_type                      AS ""VerdictType"",
                CAST(fc.severity_score AS integer)   AS ""SeverityScore"",
                a.published_at                       AS ""PublishedAt"",
                a.url                                AS ""Url""
            FROM fact_checks fc
            JOIN articles a ON a.id = fc.article_id
            JOIN outlets o  ON o.id = a.outlet_id
            WHERE o.outlet_type = 'fact_checker'
              AND (@verdict IS NULL OR fc.verdict = @verdict)
            ORDER BY a.published_at DESC
            LIMIT @pageSize OFFSET ((@page - 1) * @pageSize)";

        var items = await _context.Database
            .SqlQueryRaw<FactCheckListItemDto>(
                dataSql,
                new NpgsqlParameter("@verdict", NpgsqlDbType.Varchar) { Value = verdictValue },
                new NpgsqlParameter("@pageSize", pageSize),
                new NpgsqlParameter("@page", page))
            .ToListAsync(ct);

        return new PaginatedResultDto<FactCheckListItemDto>
        {
            Items = items,
            TotalCount = totalCount,
            Page = page,
            PageSize = pageSize
        };
    }

    public async Task<FactCheckBadgeDto?> GetBadgeForClusterAsync(
        int clusterRunId,
        int clusterId,
        CancellationToken ct)
    {
        _logger.LogInformation(
            "Fetching fact-check badge for cluster run={ClusterRunId}, cluster={ClusterId}",
            clusterRunId, clusterId);

        var sql = @"
            SELECT
                ecff.has_tier1_match                        AS ""HasTier1Match"",
                ecff.has_tier2_match                        AS ""HasTier2Match"",
                CAST(ecff.factcheck_count AS integer)       AS ""FactcheckCount"",
                CAST(ecff.max_severity    AS integer)       AS ""MaxSeverity"",
                fc.id                                       AS ""Id"",
                fc.article_id                               AS ""ArticleId"",
                a.title                                     AS ""Title"",
                o.name                                      AS ""OutletName"",
                fc.verdict                                  AS ""Verdict"",
                fc.verdict_type                             AS ""VerdictType"",
                CAST(fc.severity_score AS integer)          AS ""SeverityScore"",
                a.published_at                              AS ""PublishedAt"",
                a.url                                       AS ""Url""
            FROM event_cluster_factcheck_flags ecff
            JOIN factcheck_cluster_map fcm
                ON  fcm.cluster_run_id = ecff.cluster_run_id
                AND fcm.cluster_id     = ecff.cluster_id
            JOIN fact_checks fc ON fc.id = fcm.factcheck_id
            JOIN articles    a  ON a.id  = fc.article_id
            JOIN outlets     o  ON o.id  = a.outlet_id
            WHERE ecff.cluster_run_id = @clusterRunId
              AND ecff.cluster_id     = @clusterId";

        var rows = await _context.Database
            .SqlQueryRaw<BadgeRawRow>(
                sql,
                new NpgsqlParameter("@clusterRunId", clusterRunId),
                new NpgsqlParameter("@clusterId", clusterId))
            .ToListAsync(ct);

        if (rows.Count == 0)
            return null;

        var first = rows[0];

        var linkedFactChecks = rows
            .Select(r => new FactCheckListItemDto(
                r.Id,
                r.ArticleId,
                r.Title,
                r.OutletName,
                r.Verdict,
                r.VerdictType,
                r.SeverityScore,
                r.PublishedAt,
                r.Url))
            .ToList();

        return new FactCheckBadgeDto(
            first.HasTier1Match,
            first.HasTier2Match,
            first.FactcheckCount,
            first.MaxSeverity,
            linkedFactChecks);
    }
}

internal sealed record BadgeRawRow(
    bool HasTier1Match,
    bool HasTier2Match,
    int FactcheckCount,
    int? MaxSeverity,
    long Id,
    long ArticleId,
    string Title,
    string OutletName,
    string Verdict,
    string VerdictType,
    int? SeverityScore,
    DateTime PublishedAt,
    string? Url
);
