using Microsoft.EntityFrameworkCore;
using PrismaAPI.Data;
using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public class AnalysisService : IAnalysisService
{
    private readonly PrismaDbContext _context;
    private readonly ILogger<AnalysisService> _logger;

    public AnalysisService(PrismaDbContext context, ILogger<AnalysisService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<List<BiasChartPointDto>> GetBiasChartAsync()
    {
        _logger.LogInformation("Fetching bias chart data");

        return await _context.Articles
            .AsNoTracking()
            .Where(a => a.TfGovStanceConf != null && a.TfSovereignismConf != null)
            .GroupBy(a => a.OutletId)
            .Select(g => new
            {
                OutletId = g.Key,
                AvgCoalition = g.Average(a => (double)a.TfGovStanceConf!.Value),
                AvgEuAxis = g.Average(a => (double)a.TfSovereignismConf!.Value),
                ArticleCount = g.Count()
            })
            .Join(_context.Outlets.AsNoTracking(),
                x => x.OutletId, o => o.Id,
                (x, o) => new BiasChartPointDto
                {
                    OutletName = o.Name,
                    OutletType = o.OutletType,
                    AvgCoalition = x.AvgCoalition,
                    AvgEuAxis = x.AvgEuAxis,
                    ArticleCount = x.ArticleCount
                })
            .ToListAsync();
    }

    public async Task<List<ScoresComparisonDto>> GetScoresComparisonAsync()
    {
        _logger.LogInformation("Fetching scores comparison data");

        return await _context.Articles
            .AsNoTracking()
            .Where(a => a.ScoreSensationalism != null
                      || a.ScoreCitationQuality != null
                      || a.ScoreRhetoricIntensity != null)
            .GroupBy(a => a.OutletId)
            .Select(g => new
            {
                OutletId = g.Key,
                AvgSensationalism = g.Average(a => a.ScoreSensationalism),
                AvgCitationQuality = g.Average(a => a.ScoreCitationQuality),
                AvgRhetoricIntensity = g.Average(a => a.ScoreRhetoricIntensity)
            })
            .Join(_context.Outlets.AsNoTracking(),
                x => x.OutletId, o => o.Id,
                (x, o) => new ScoresComparisonDto
                {
                    OutletName = o.Name,
                    OutletType = o.OutletType,
                    AvgSensationalism = x.AvgSensationalism,
                    AvgCitationQuality = x.AvgCitationQuality,
                    AvgRhetoricIntensity = x.AvgRhetoricIntensity
                })
            .ToListAsync();
    }

    public async Task<List<TopicDistributionDto>> GetTopicDistributionAsync()
    {
        _logger.LogInformation("Fetching topic distribution data");

        var topicCounts = await _context.Articles
            .AsNoTracking()
            .Where(a => a.TfTopic != null)
            .GroupBy(a => new { a.OutletId, a.TfTopic })
            .Select(g => new
            {
                g.Key.OutletId,
                Topic = g.Key.TfTopic!,
                Count = g.Count()
            })
            .ToListAsync();

        var outletNames = await _context.Outlets
            .AsNoTracking()
            .ToDictionaryAsync(o => o.Id, o => o.Name);

        return topicCounts
            .GroupBy(x => x.OutletId)
            .Select(outletGroup =>
            {
                var total = (double)outletGroup.Sum(x => x.Count);
                var lookup = outletGroup.ToDictionary(x => x.Topic, x => x.Count);

                double Pct(string topic) => lookup.TryGetValue(topic, out var c) ? Math.Round(c / total * 100, 2) : 0;

                return new TopicDistributionDto
                {
                    OutletName = outletNames.GetValueOrDefault(outletGroup.Key, "Unknown"),
                    PoliticsPct = Pct("politics"),
                    EconomyPct = Pct("economy"),
                    ForeignAffairsPct = Pct("foreign_affairs"),
                    JusticePct = Pct("justice"),
                    HealthPct = Pct("health"),
                    SportsPct = Pct("sports"),
                    CulturePct = Pct("culture"),
                    SocialPct = Pct("social"),
                    EnvironmentPct = Pct("environment"),
                    TechnologyPct = Pct("technology")
                };
            })
            .ToList();
    }

    public async Task<List<FramingDistributionDto>> GetFramingDistributionAsync()
    {
        _logger.LogInformation("Fetching framing distribution data");

        var framingCounts = await _context.Articles
            .AsNoTracking()
            .Where(a => a.TfFraming != null)
            .GroupBy(a => new { a.OutletId, a.TfFraming })
            .Select(g => new
            {
                g.Key.OutletId,
                Framing = g.Key.TfFraming!,
                Count = g.Count()
            })
            .ToListAsync();

        var outletNames = await _context.Outlets
            .AsNoTracking()
            .ToDictionaryAsync(o => o.Id, o => o.Name);

        return framingCounts
            .GroupBy(x => x.OutletId)
            .Select(outletGroup =>
            {
                var total = (double)outletGroup.Sum(x => x.Count);
                var lookup = outletGroup.ToDictionary(x => x.Framing, x => x.Count);

                double Pct(string framing) => lookup.TryGetValue(framing, out var c) ? Math.Round(c / total * 100, 2) : 0;

                return new FramingDistributionDto
                {
                    OutletName = outletNames.GetValueOrDefault(outletGroup.Key, "Unknown"),
                    NeutralPct = Pct("neutral"),
                    SupportivePct = Pct("supportive"),
                    CriticalPct = Pct("critical"),
                    AlarmistPct = Pct("alarmist"),
                    HumanInterestPct = Pct("human_interest")
                };
            })
            .ToList();
    }

    public async Task<List<CoverageGapDto>> GetCoverageGapsAsync(int? runId)
    {
        _logger.LogInformation("Fetching coverage gaps for run {RunId}", runId);

        var resolvedRunId = runId ?? await _context.ClusterRuns
            .AsNoTracking()
            .OrderByDescending(r => r.CreatedAt)
            .Select(r => r.Id)
            .FirstOrDefaultAsync();

        if (resolvedRunId == 0) return new List<CoverageGapDto>();

        var allOutlets = await _context.Outlets
            .AsNoTracking()
            .Select(o => o.Name)
            .ToListAsync();

        var clusterLabels = await _context.ClusterLabels
            .AsNoTracking()
            .Where(cl => cl.ClusterRunId == resolvedRunId && !cl.IsEventCluster)
            .ToDictionaryAsync(cl => cl.ClusterId, cl => cl.LabelText);

        var outletsByCluster = await _context.Articles
            .AsNoTracking()
            .Where(a => a.ClusterRunId == resolvedRunId && a.ClusterId != null)
            .GroupBy(a => a.ClusterId!.Value)
            .Select(g => new
            {
                ClusterId = g.Key,
                OutletIds = g.Select(a => a.OutletId).Distinct().ToList()
            })
            .ToListAsync();

        var outletNameLookup = await _context.Outlets
            .AsNoTracking()
            .ToDictionaryAsync(o => o.Id, o => o.Name);

        return outletsByCluster.Select(cluster =>
        {
            var presentOutlets = cluster.OutletIds
                .Select(id => outletNameLookup.GetValueOrDefault(id, "Unknown"))
                .ToList();

            var missingOutlets = allOutlets.Except(presentOutlets).ToList();

            return new CoverageGapDto
            {
                ClusterId = cluster.ClusterId,
                ClusterLabel = clusterLabels.GetValueOrDefault(cluster.ClusterId),
                TotalOutlets = allOutlets.Count,
                CoveringOutlets = presentOutlets.Count,
                PresentOutlets = presentOutlets,
                MissingOutlets = missingOutlets
            };
        }).ToList();
    }

    public async Task<PaginatedResultDto<LlmVsXgboostDto>> GetLlmVsXgboostAsync(
        int? outletId, int page = 1, int pageSize = 20)
    {
        _logger.LogInformation(
            "Fetching LLM vs XGBoost comparison: outletId={OutletId}, page={Page}", outletId, page);

        pageSize = Math.Clamp(pageSize, 1, 100);
        page = Math.Max(1, page);

        var query = _context.Articles
            .AsNoTracking()
            .Where(a => a.LlmCoalition != null && a.TfGovStanceConf != null);

        if (outletId.HasValue)
            query = query.Where(a => a.OutletId == outletId.Value);

        var totalCount = await query.CountAsync();

        var items = await query
            .OrderByDescending(a => a.PublishedAt)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(a => new LlmVsXgboostDto
            {
                ArticleId = a.Id,
                Title = a.Title,
                LlmCoalition = a.LlmCoalition,
                LlmEuAxis = a.LlmEuAxis,
                TfGovStanceConf = a.TfGovStanceConf,
                TfSovereignismConf = a.TfSovereignismConf,
                LlmFraming = a.LlmFraming,
                TfTopic = a.TfTopic
            })
            .ToListAsync();

        return new PaginatedResultDto<LlmVsXgboostDto>
        {
            Items = items,
            TotalCount = totalCount,
            Page = page,
            PageSize = pageSize
        };
    }
}
