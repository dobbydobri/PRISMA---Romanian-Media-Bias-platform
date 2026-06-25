using Microsoft.EntityFrameworkCore;
using PrismaAPI.Data;
using PrismaAPI.DTOs;
using PrismaAPI.Models;

namespace PrismaAPI.Services;

public class OutletService
{
    private readonly PrismaDbContext _context;
    private readonly ILogger<OutletService> _logger;

    public OutletService(PrismaDbContext context, ILogger<OutletService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<List<OutletSummaryDto>> GetAllAsync()
    {
        _logger.LogInformation("Fetching all outlets with aggregated statistics");

        var articleStats = await _context.Articles
            .AsNoTracking()
            .GroupBy(a => a.OutletId)
            .Select(g => new
            {
                OutletId = g.Key,
                TotalArticles = g.Count(),
                PoliticalArticles = 0, // Not available anymore
                AvgCoalition = g.Where(a => a.TfGovStanceConf != null)
                                 .Average(a => (double?)a.TfGovStanceConf),
                AvgEuAxis = g.Where(a => a.TfSovereignismConf != null)
                              .Average(a => (double?)a.TfSovereignismConf),
                AvgSensationalism = g.Where(a => a.ScoreSensationalism != null)
                                      .Average(a => (double?)a.ScoreSensationalism),
                AvgCitationQuality = g.Where(a => a.ScoreCitationQuality != null)
                                       .Average(a => (double?)a.ScoreCitationQuality),
                AvgRhetoricIntensity = g.Where(a => a.ScoreRhetoricIntensity != null)
                                         .Average(a => (double?)a.ScoreRhetoricIntensity),
            })
            .ToListAsync();

        var dominantTopics = await _context.Articles
            .AsNoTracking()
            .Where(a => a.TfTopic != null)
            .GroupBy(a => new { a.OutletId, a.TfTopic })
            .Select(g => new { g.Key.OutletId, Topic = g.Key.TfTopic, Count = g.Count() })
            .ToListAsync();

        var topicByOutlet = dominantTopics
            .GroupBy(x => x.OutletId)
            .ToDictionary(
                g => g.Key,
                g => g.OrderByDescending(x => x.Count).First().Topic);

        var dominantFramings = await _context.Articles
            .AsNoTracking()
            .Where(a => a.TfFraming != null)
            .GroupBy(a => new { a.OutletId, a.TfFraming })
            .Select(g => new { g.Key.OutletId, Framing = g.Key.TfFraming, Count = g.Count() })
            .ToListAsync();

        var framingByOutlet = dominantFramings
            .GroupBy(x => x.OutletId)
            .ToDictionary(
                g => g.Key,
                g => g.OrderByDescending(x => x.Count).First().Framing);

        var outlets = await _context.Outlets
            .AsNoTracking()
            .OrderBy(o => o.Name)
            .ToListAsync();

        var statsLookup = articleStats.ToDictionary(s => s.OutletId);

        return outlets.Select(o =>
        {
            statsLookup.TryGetValue(o.Id, out var stats);
            topicByOutlet.TryGetValue(o.Id, out var dominantTopic);
            framingByOutlet.TryGetValue(o.Id, out var dominantFraming);

            return new OutletSummaryDto
            {
                Id = o.Id,
                Name = o.Name,
                OutletType = o.OutletType,
                Url = o.BaseUrl,
                TotalArticles = stats?.TotalArticles ?? 0,
                PoliticalArticles = stats?.PoliticalArticles ?? 0,
                AvgCoalition = stats?.AvgCoalition,
                AvgEuAxis = stats?.AvgEuAxis,
                AvgSensationalism = stats?.AvgSensationalism,
                AvgCitationQuality = stats?.AvgCitationQuality,
                AvgRhetoricIntensity = stats?.AvgRhetoricIntensity,
                DominantTopic = dominantTopic,
                DominantFraming = dominantFraming,
            };
        }).ToList();
    }
}
