using Microsoft.EntityFrameworkCore;
using PrismaAPI.Data;
using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public class ConnectionsService : IConnectionsService
{
    private readonly PrismaDbContext _context;
    private readonly ILogger<ConnectionsService> _logger;

    public ConnectionsService(PrismaDbContext context, ILogger<ConnectionsService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<List<EntityConnectionDto>> GetEntityConnectionsAsync(
        string entityName, int limit = 50)
    {
        _logger.LogInformation("Finding connections for entity: {EntityName}", entityName);

        limit = Math.Clamp(limit, 1, 200);

        var asSource = await _context.EntityConnections
            .AsNoTracking()
            .Where(e => e.SourceEntity == entityName)
            .Select(e => new EntityConnectionDto
            {
                EntityName = e.TargetEntity,
                EntityLabel = e.TargetLabel,
                CoMentionCount = e.WeightRaw,
                WeightPmi = e.WeightPmi
            })
            .ToListAsync();

        var asTarget = await _context.EntityConnections
            .AsNoTracking()
            .Where(e => e.TargetEntity == entityName)
            .Select(e => new EntityConnectionDto
            {
                EntityName = e.SourceEntity,
                EntityLabel = e.SourceLabel,
                CoMentionCount = e.WeightRaw,
                WeightPmi = e.WeightPmi
            })
            .ToListAsync();

        return asSource
            .Concat(asTarget)
            .OrderByDescending(x => x.WeightPmi)
            .Take(limit)
            .ToList();
    }

    public async Task<List<EntityArticleDto>> GetEntityArticlesAsync(string entityName)
    {
        _logger.LogInformation("Finding articles mentioning entity: {EntityName}", entityName);

        // Single query: join article_entities_full → articles → outlets in one round-trip.
        return await _context.ArticleEntitiesFull
            .AsNoTracking()
            .Where(e => e.EntityText == entityName)
            .Select(e => e.ArticleId)
            .Distinct()
            .Join(
                _context.Articles.AsNoTracking(),
                entityArticleId => (long)entityArticleId,
                a => a.Id,
                (_, a) => a)
            .Join(
                _context.Outlets.AsNoTracking(),
                a => a.OutletId,
                o => o.Id,
                (a, o) => new EntityArticleDto
                {
                    ArticleId = a.Id,
                    Title = a.Title,
                    OutletName = o.Name,
                    PublishedAt = a.PublishedAt
                })
            .OrderByDescending(a => a.PublishedAt)
            .Take(50)
            .ToListAsync();
    }
}
