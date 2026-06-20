using Microsoft.EntityFrameworkCore;
using PrismaAPI.Data;
using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public class ConnectionsService
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

    public async Task<EntityPathDto?> FindPathAsync(string fromEntity, string toEntity)
    {
        _logger.LogInformation("Finding path from {From} to {To}", fromEntity, toEntity);

        const int maxDepth = 6;

        if (fromEntity == toEntity)
            return new EntityPathDto { Path = new List<string> { fromEntity }, TotalDistance = 0 };

        var visited = new HashSet<string> { fromEntity };
        var queue = new Queue<List<string>>();
        queue.Enqueue(new List<string> { fromEntity });

        while (queue.Count > 0)
        {
            var path = queue.Dequeue();

            if (path.Count >= maxDepth)
                continue;

            var current = path.Last();

            var neighbors = await _context.EntityConnections
                .AsNoTracking()
                .Where(e => e.SourceEntity == current || e.TargetEntity == current)
                .Select(e => e.SourceEntity == current ? e.TargetEntity : e.SourceEntity)
                .Distinct()
                .ToListAsync();

            foreach (var neighbor in neighbors)
            {
                if (visited.Contains(neighbor)) continue;
                visited.Add(neighbor);

                var newPath = new List<string>(path) { neighbor };

                if (neighbor == toEntity)
                    return new EntityPathDto
                    {
                        Path = newPath,
                        TotalDistance = newPath.Count - 1
                    };

                queue.Enqueue(newPath);
            }
        }

        _logger.LogWarning("No path found between {From} and {To} within {MaxDepth} hops",
            fromEntity, toEntity, maxDepth);
        return null;
    }

    public async Task<List<EntityArticleDto>> GetEntityArticlesAsync(string entityName)
    {
        _logger.LogInformation("Finding articles mentioning entity: {EntityName}", entityName);

        var articleIds = await _context.ArticleEntitiesFull
            .AsNoTracking()
            .Where(e => e.EntityText == entityName)
            .Select(e => e.ArticleId)
            .Distinct()
            .ToListAsync();

        if (articleIds.Count == 0)
            return new List<EntityArticleDto>();

        var longIds = articleIds.Select(id => (long)id).ToList();

        return await _context.Articles
            .AsNoTracking()
            .Where(a => longIds.Contains(a.Id))
            .Join(_context.Outlets.AsNoTracking(),
                a => a.OutletId, o => o.Id,
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
