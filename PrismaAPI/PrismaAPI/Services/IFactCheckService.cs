using PrismaAPI.DTOs;
using PrismaAPI.DTOs.FactCheck;

namespace PrismaAPI.Services;

public interface IFactCheckService
{
    Task<PaginatedResultDto<FactCheckListItemDto>> GetListAsync(
        int page,
        int pageSize,
        string? verdict,
        CancellationToken ct);

    Task<List<FactCheckClusterDto>> GetByClusterAsync(int runId, int clusterId);

    Task<List<FactCheckProximityDto>> GetProximityAsync(
        long articleId,
        double threshold = 0.7,
        int limit = 10);

    Task<List<FactCheckDto>> GetByArticleAsync(long articleId);

    Task<FactCheckBadgeDto?> GetBadgeForClusterAsync(
        int clusterRunId,
        int clusterId,
        CancellationToken ct);
}
