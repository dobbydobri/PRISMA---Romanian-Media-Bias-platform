using Microsoft.EntityFrameworkCore;
using PrismaAPI.Data;
using PrismaAPI.DTOs;
using PrismaAPI.Models;

namespace PrismaAPI.Services;

public class ArticleService
{
    private readonly PrismaDbContext _context;
    private readonly ILogger<ArticleService> _logger;

    public ArticleService(PrismaDbContext context, ILogger<ArticleService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<PaginatedResultDto<ArticleListDto>> GetAllAsync(
        int? outletId,
        string? topic,
        string? framing,
        int page = 1,
        int pageSize = 20)
    {
        pageSize = Math.Clamp(pageSize, 1, 100);
        page = Math.Max(1, page);

        _logger.LogInformation(
            "Listing articles – outletId={OutletId}, topic={Topic}, framing={Framing}, page={Page}, pageSize={PageSize}",
            outletId, topic, framing, page, pageSize);

        var query = _context.Articles.AsNoTracking().AsQueryable();

        if (outletId.HasValue)
            query = query.Where(a => a.OutletId == outletId.Value);

        if (!string.IsNullOrWhiteSpace(topic))
            query = query.Where(a => a.TfTopic == topic);

        if (!string.IsNullOrWhiteSpace(framing))
            query = query.Where(a => a.LlmFraming == framing);

        var totalCount = await query.CountAsync();

        var items = await query
            .OrderByDescending(a => a.PublishedAt)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Join(
                _context.Outlets.AsNoTracking(),
                a => a.OutletId,
                o => o.Id,
                (a, o) => new { Article = a, OutletName = o.Name })
            .GroupJoin(
                _context.ClusterLabels.AsNoTracking(),
                ao => new { ClusterRunId = ao.Article.ClusterRunId ?? 0, ClusterId = ao.Article.ClusterId ?? -1 },
                cl => new { ClusterRunId = cl.ClusterRunId, ClusterId = cl.ClusterId },
                (ao, labels) => new { ao.Article, ao.OutletName, Labels = labels })
            .SelectMany(
                x => x.Labels.DefaultIfEmpty(),
                (x, cl) => new ArticleListDto
                {
                    Id = x.Article.Id,
                    Title = x.Article.Title,
                    Url = x.Article.Url,
                    OutletName = x.OutletName,
                    PublishedAt = x.Article.PublishedAt,
                    ClusterId = x.Article.ClusterId,
                    ClusterLabel = cl != null ? cl.LabelText : null,
                    ScoreSensationalism = x.Article.ScoreSensationalism,
                    ScoreCitationQuality = x.Article.ScoreCitationQuality,
                    ScoreRhetoricIntensity = x.Article.ScoreRhetoricIntensity,
                    TfGovStance = x.Article.TfGovStance,
                    TfSovereignism = x.Article.TfSovereignism,
                    TfFraming = x.Article.TfFraming,
                    TfTopic = x.Article.TfTopic,
                })
            .ToListAsync();

        return new PaginatedResultDto<ArticleListDto>
        {
            Items = items,
            TotalCount = totalCount,
            Page = page,
            PageSize = pageSize,
        };
    }

    public async Task<ArticleDetailDto?> GetByIdAsync(long id)
    {
        _logger.LogInformation("Fetching article detail for id={ArticleId}", id);

        var article = await _context.Articles
            .AsNoTracking()
            .Include(a => a.Outlet)
            .Include(a => a.ArticleEntities)
            .FirstOrDefaultAsync(a => a.Id == id);

        if (article is null)
            return null;

        ClusterLabel? clusterLabel = null;
        if (article.ClusterRunId.HasValue && article.ClusterId.HasValue)
        {
            clusterLabel = await _context.ClusterLabels
                .AsNoTracking()
                .FirstOrDefaultAsync(cl =>
                    cl.ClusterRunId == article.ClusterRunId.Value &&
                    cl.ClusterId == article.ClusterId.Value);
        }

        var factCheck = await _context.FactChecks
            .AsNoTracking()
            .Where(fc => fc.ArticleId == id)
            .Select(fc => new FactCheckDto
            {
                Id = fc.Id,
                ArticleId = fc.ArticleId,
                ArticleTitle = article.Title,
                OutletName = article.Outlet.Name,
                Verdict = fc.Verdict,
                VerdictType = fc.VerdictType,
                ClaimText = fc.ClaimText,
                RawVerdict = fc.RawVerdict,
                PublishedAt = fc.PublishedAt,
            })
            .ToListAsync();

        return new ArticleDetailDto
        {
            Id = article.Id,
            Title = article.Title,
            ContentText = article.ContentText,
            Url = article.Url,
            OutletName = article.Outlet.Name,
            OutletId = article.OutletId,
            PublishedAt = article.PublishedAt,
            Authors = article.Authors,
            ScoreSensationalism = article.ScoreSensationalism,
            ScoreCitationQuality = article.ScoreCitationQuality,
            ScoreRhetoricIntensity = article.ScoreRhetoricIntensity,
            TfGovStance = article.TfGovStance,
            TfSovereignism = article.TfSovereignism,
            TfFraming = article.TfFraming,
            TfTopic = article.TfTopic,
            ClusterId = article.ClusterId,
            SubClusterId = article.SubClusterId,
            ClusterLabel = clusterLabel?.LabelText,
            ClusterTerms = clusterLabel?.TopTfidfTerms,
            ClusterEntities = clusterLabel?.TopEntities,
            Entities = article.ArticleEntities.Select(e => new ArticleEntityDto
            {
                EntityText = e.EntityText,
                EntityLabel = e.EntityLabel,
            }).ToList(),
            RelatedFactChecks = factCheck.Count > 0 ? factCheck : null,
        };
    }
}
