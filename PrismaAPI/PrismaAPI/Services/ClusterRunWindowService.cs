using Microsoft.EntityFrameworkCore;
using PrismaAPI.Data;
using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public class ClusterRunWindowService : IClusterRunWindowService
{
    private readonly PrismaDbContext _context;
    private readonly ILogger<ClusterRunWindowService> _logger;

    public ClusterRunWindowService(PrismaDbContext context, ILogger<ClusterRunWindowService> logger)
    {
        _context = context;
        _logger = logger;
    }

    public async Task<List<ClusterRunWindowDto>> GetByRunIdAsync(int runId)
    {
        _logger.LogInformation("Fetching cluster run windows for run {RunId}", runId);

        return await _context.ClusterRunWindows
            .AsNoTracking()
            .Where(w => w.RunId == runId)
            .OrderBy(w => w.WindowStart)
            .Select(w => new ClusterRunWindowDto
            {
                Id = w.Id,
                RunId = w.RunId,
                WindowStart = w.WindowStart,
                WindowEnd = w.WindowEnd,
                ArticlesIn = w.ArticlesIn,
                NClusters = w.NClusters,
                NNoise = w.NNoise,
                Dbcv = w.Dbcv
            })
            .ToListAsync();
    }

    public async Task<List<ClusterRunWindowDto>> GetLatestAsync()
    {
        _logger.LogInformation("Fetching cluster run windows for latest run");

        var latestRunId = await _context.ClusterRuns
            .AsNoTracking()
            .OrderByDescending(r => r.CreatedAt)
            .Select(r => r.Id)
            .FirstOrDefaultAsync();

        if (latestRunId == 0)
        {
            return new List<ClusterRunWindowDto>();
        }

        return await GetByRunIdAsync(latestRunId);
    }
}
