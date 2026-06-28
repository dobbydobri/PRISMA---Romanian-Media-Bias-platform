using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public interface IClusterRunWindowService
{
    Task<List<ClusterRunWindowDto>> GetByRunIdAsync(int runId);
    Task<List<ClusterRunWindowDto>> GetLatestAsync();
}
