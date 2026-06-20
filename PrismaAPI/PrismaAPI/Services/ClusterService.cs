using Microsoft.EntityFrameworkCore;
using PrismaAPI.Data;
using PrismaAPI.DTOs;
using PrismaAPI.Models;

namespace PrismaAPI.Services;

public class ClusterService
{
    private readonly PrismaDbContext _context;
    private readonly ILogger<ClusterService> _logger;

    public ClusterService(PrismaDbContext context, ILogger<ClusterService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<PaginatedResultDto<ClusterListDto>> GetAllAsync(
        string? runId,
        bool? isEvent,
        int page = 1,
        int pageSize = 20,
        string sortBy = "articleCount")
    {
        pageSize = Math.Clamp(pageSize, 1, 100);
        page = Math.Max(1, page);

        int resolvedRunId = await ResolveRunIdAsync(runId);

        _logger.LogInformation(
            "Listing clusters – runId={RunId}, isEvent={IsEvent}, page={Page}, sortBy={SortBy}",
            resolvedRunId, isEvent, page, sortBy);

        var query = _context.ClusterLabels
            .AsNoTracking()
            .Where(cl => cl.ClusterRunId == resolvedRunId);

        if (isEvent.HasValue)
            query = query.Where(cl => cl.IsEventCluster == isEvent.Value);

        query = sortBy.ToLowerInvariant() switch
        {
            "datefrom" => query.OrderBy(cl => cl.DateFrom),
            "outletcount" => query.OrderByDescending(cl => cl.OutletCount),
            _ => query.OrderByDescending(cl => cl.ArticleCount), // "articleCount" default
        };

        var totalCount = await query.CountAsync();

        var items = await query
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(cl => new ClusterListDto
            {
                ClusterId = cl.ClusterId,
                RunId = cl.ClusterRunId,
                LabelText = cl.LabelText,
                TopTfidfTerms = cl.TopTfidfTerms,
                TopEntities = cl.TopEntities,
                ArticleCount = cl.ArticleCount,
                OutletCount = cl.OutletCount,
                DateFrom = cl.DateFrom,
                DateTo = cl.DateTo,
                IsEventCluster = cl.IsEventCluster,
                ParentClusterId = cl.ParentClusterId,
            })
            .ToListAsync();

        return new PaginatedResultDto<ClusterListDto>
        {
            Items = items,
            TotalCount = totalCount,
            Page = page,
            PageSize = pageSize,
        };
    }

    public async Task<ClusterDetailDto?> GetDetailAsync(int runId, int clusterId)
    {
        _logger.LogInformation(
            "Fetching cluster detail – runId={RunId}, clusterId={ClusterId}",
            runId, clusterId);

        var label = await _context.ClusterLabels
            .AsNoTracking()
            .FirstOrDefaultAsync(cl =>
                cl.ClusterRunId == runId && cl.ClusterId == clusterId);

        if (label is null)
            return null;

        var articles = await _context.Articles
            .AsNoTracking()
            .Where(a => a.ClusterRunId == runId && a.ClusterId == clusterId)
            .Join(
                _context.Outlets.AsNoTracking(),
                a => a.OutletId,
                o => o.Id,
                (a, o) => new { Article = a, OutletName = o.Name })
            .Select(x => new
            {
                x.OutletName,
                Dto = new ArticleListDto
                {
                    Id = x.Article.Id,
                    Title = x.Article.Title,
                    OutletName = x.OutletName,
                    PublishedAt = x.Article.PublishedAt,
                    ClusterId = x.Article.ClusterId,
                    ClusterLabel = label.LabelText,
                    ScoreSensationalism = x.Article.ScoreSensationalism,
                    ScoreCitationQuality = x.Article.ScoreCitationQuality,
                    ScoreRhetoricIntensity = x.Article.ScoreRhetoricIntensity,
                    PredCoalition = x.Article.PredCoalition,
                    PredEuAxis = x.Article.PredEuAxis,
                    PredIsPolitical = x.Article.PredIsPolitical,
                    LlmFraming = x.Article.LlmFraming,
                    LlmTopic = x.Article.LlmTopic,
                }
            })
            .ToListAsync();

        var articlesByOutlet = articles
            .GroupBy(x => x.OutletName)
            .ToDictionary(g => g.Key, g => g.Select(x => x.Dto).ToList());

        var factChecks = await _context.FactCheckClusterMaps
            .AsNoTracking()
            .Where(m => m.ClusterRunId == runId && m.ClusterId == clusterId)
            .Join(
                _context.FactChecks.AsNoTracking(),
                m => m.FactcheckId,
                fc => fc.Id,
                (m, fc) => fc)
            .Join(
                _context.Articles.AsNoTracking(),
                fc => fc.ArticleId,
                a => a.Id,
                (fc, a) => new { FactCheck = fc, ArticleTitle = a.Title })
            .Join(
                _context.Outlets.AsNoTracking(),
                x => x.FactCheck.OutletId,
                o => o.Id,
                (x, o) => new FactCheckDto
                {
                    Id = x.FactCheck.Id,
                    ArticleId = x.FactCheck.ArticleId,
                    ArticleTitle = x.ArticleTitle,
                    OutletName = o.Name,
                    Verdict = x.FactCheck.Verdict,
                    VerdictType = x.FactCheck.VerdictType,
                    ClaimText = x.FactCheck.ClaimText,
                    RawVerdict = x.FactCheck.RawVerdict,
                    PublishedAt = x.FactCheck.PublishedAt,
                })
            .ToListAsync();

        return new ClusterDetailDto
        {
            ClusterId = label.ClusterId,
            RunId = label.ClusterRunId,
            LabelText = label.LabelText,
            TopTfidfTerms = label.TopTfidfTerms,
            TopEntities = label.TopEntities,
            ArticleCount = label.ArticleCount,
            OutletCount = label.OutletCount,
            DateFrom = label.DateFrom,
            DateTo = label.DateTo,
            IsEventCluster = label.IsEventCluster,
            ParentClusterId = label.ParentClusterId,
            ArticlesByOutlet = articlesByOutlet,
            LinkedFactChecks = factChecks,
        };
    }


    private async Task<int> ResolveRunIdAsync(string? runId)
    {
        if (string.IsNullOrWhiteSpace(runId) ||
            runId.Equals("latest", StringComparison.OrdinalIgnoreCase))
        {
            return await _context.ClusterRuns
                .AsNoTracking()
                .OrderByDescending(cr => cr.Id)
                .Select(cr => cr.Id)
                .FirstOrDefaultAsync();
        }

        if (int.TryParse(runId, out var parsed))
            return parsed;

        _logger.LogWarning("Invalid runId '{RunId}', falling back to latest", runId);
        return await _context.ClusterRuns
            .AsNoTracking()
            .OrderByDescending(cr => cr.Id)
            .Select(cr => cr.Id)
            .FirstOrDefaultAsync();
    }
}
