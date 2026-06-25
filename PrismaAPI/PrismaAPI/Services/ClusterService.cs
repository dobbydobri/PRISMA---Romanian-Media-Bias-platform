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
        string sortBy = "articleCount",
        DateTime? dateFrom = null,
        DateTime? dateTo = null)
    {
        pageSize = Math.Clamp(pageSize, 1, 100);
        page = Math.Max(1, page);

        int resolvedRunId = await ResolveRunIdAsync(runId);

        _logger.LogInformation(
            "Listing clusters – runId={RunId}, isEvent={IsEvent}, page={Page}, sortBy={SortBy}",
            resolvedRunId, isEvent, page, sortBy);

        var baseQuery = _context.ClusterLabels
            .AsNoTracking()
            .Where(cl => cl.ClusterRunId == resolvedRunId);

        if (isEvent.HasValue)
            baseQuery = baseQuery.Where(cl => cl.IsEventCluster == isEvent.Value);

        if (dateFrom.HasValue)
        {
            var dateFromOnly = DateOnly.FromDateTime(dateFrom.Value);
            baseQuery = baseQuery.Where(cl => cl.DateTo >= dateFromOnly);
        }

        if (dateTo.HasValue)
        {
            var dateToOnly = DateOnly.FromDateTime(dateTo.Value);
            baseQuery = baseQuery.Where(cl => cl.DateFrom <= dateToOnly);
        }

        // Filter out clusters that have NO non-excluded articles, since we only take into account non-excluded ones.
        if (isEvent == true)
        {
            baseQuery = baseQuery.Where(cl => _context.Articles.Any(a => a.ClusterRunId == cl.ClusterRunId && a.SubClusterId == cl.ClusterId && a.IsExcluded != true));
        }
        else if (isEvent == false)
        {
            baseQuery = baseQuery.Where(cl => _context.Articles.Any(a => a.ClusterRunId == cl.ClusterRunId && a.ClusterId == cl.ClusterId && a.IsExcluded != true));
        }
        else
        {
            baseQuery = baseQuery.Where(cl => _context.Articles.Any(a => a.ClusterRunId == cl.ClusterRunId && 
                (cl.IsEventCluster ? a.SubClusterId == cl.ClusterId : a.ClusterId == cl.ClusterId) && 
                a.IsExcluded != true));
        }

        // GroupJoin with ClusterSummaries to get ClusterTitle
        var query = baseQuery.GroupJoin(
            _context.ClusterSummaries.AsNoTracking(),
            cl => new { cl.ClusterRunId, cl.ClusterId },
            cs => new { cs.ClusterRunId, cs.ClusterId },
            (cl, csGroup) => new { Cluster = cl, Summary = csGroup.FirstOrDefault() }
        );

        var preFilterCount = await query.CountAsync();
        _logger.LogInformation("Clusters before filter: {PreFilterCount}", preFilterCount);

        if (isEvent == true)
        {
            query = query.Where(x => x.Cluster.OutletCount > 1 && x.Summary != null);
            var postFilterCount = await query.CountAsync();
            _logger.LogInformation("Clusters after filter (OutletCount > 1 && Summary != null): {PostFilterCount}", postFilterCount);
        }

        query = sortBy.ToLowerInvariant() switch
        {
            "datefrom" => query.OrderBy(x => x.Cluster.DateFrom),
            "outletcount" => query.OrderByDescending(x => x.Cluster.OutletCount),
            "recent" => isEvent == true 
                ? query.OrderByDescending(x => _context.Articles
                    .Where(a => a.ClusterRunId == x.Cluster.ClusterRunId && a.SubClusterId == x.Cluster.ClusterId && a.IsExcluded != true)
                    .Max(a => a.PublishedAt))
                : (isEvent == false 
                    ? query.OrderByDescending(x => _context.Articles
                        .Where(a => a.ClusterRunId == x.Cluster.ClusterRunId && a.ClusterId == x.Cluster.ClusterId && a.IsExcluded != true)
                        .Max(a => a.PublishedAt))
                    : query.OrderByDescending(x => _context.Articles
                        .Where(a => a.ClusterRunId == x.Cluster.ClusterRunId && 
                                    (x.Cluster.IsEventCluster ? a.SubClusterId == x.Cluster.ClusterId : a.ClusterId == x.Cluster.ClusterId) && 
                                    a.IsExcluded != true)
                        .Max(a => a.PublishedAt))),
            _ => query.OrderByDescending(x => x.Cluster.ArticleCount), // "articleCount" default
        };

        var totalCount = await query.CountAsync();

        var items = await query
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(x => new ClusterListDto
            {
                ClusterId = x.Cluster.ClusterId,
                RunId = x.Cluster.ClusterRunId,
                LabelText = x.Cluster.LabelText,
                TopTfidfTerms = x.Cluster.TopTfidfTerms,
                TopEntities = x.Cluster.TopEntities,
                ArticleCount = x.Cluster.ArticleCount,
                OutletCount = x.Cluster.OutletCount,
                DateFrom = x.Cluster.DateFrom,
                DateTo = x.Cluster.DateTo,
                IsEventCluster = x.Cluster.IsEventCluster,
                ParentClusterId = x.Cluster.ParentClusterId,
                ClusterTitle = x.Summary != null ? x.Summary.ClusterTitle : null
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
            .Where(a => a.ClusterRunId == runId && 
                        (label.IsEventCluster ? a.SubClusterId == clusterId : a.ClusterId == clusterId))
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
                    Url = x.Article.Url,
                    OutletName = x.OutletName,
                    PublishedAt = x.Article.PublishedAt,
                    ClusterId = x.Article.ClusterId,
                    ClusterLabel = label.LabelText,
                    ScoreSensationalism = x.Article.ScoreSensationalism,
                    ScoreCitationQuality = x.Article.ScoreCitationQuality,
                    ScoreRhetoricIntensity = x.Article.ScoreRhetoricIntensity,
                    TfGovStance = x.Article.TfGovStance,
                    TfSovereignism = x.Article.TfSovereignism,
                    TfFraming = x.Article.TfFraming,
                    TfTopic = x.Article.TfTopic,
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

    public async Task<ClusterSummaryDto?> GetSummaryAsync(int runId, int clusterId)
    {
        _logger.LogInformation(
            "Fetching cluster summary – runId={RunId}, clusterId={ClusterId}",
            runId, clusterId);

        var summary = await _context.ClusterSummaries
            .AsNoTracking()
            .FirstOrDefaultAsync(cs => cs.ClusterRunId == runId && cs.ClusterId == clusterId);

        if (summary is null)
            return null;

        var keyPoints = new List<string>();
        if (!string.IsNullOrWhiteSpace(summary.KeyPoints))
        {
            try
            {
                var parsed = System.Text.Json.JsonSerializer.Deserialize<List<string>>(summary.KeyPoints);
                if (parsed != null)
                {
                    keyPoints = parsed;
                }
            }
            catch (System.Text.Json.JsonException ex)
            {
                _logger.LogWarning(ex, "Failed to parse KeyPoints JSON for runId={RunId}, clusterId={ClusterId}. Raw value: {RawValue}", runId, clusterId, summary.KeyPoints);
            }
        }

        return new ClusterSummaryDto
        {
            ClusterTitle = summary.ClusterTitle,
            NeutralSummary = summary.SummaryText,
            KeyPoints = keyPoints
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
