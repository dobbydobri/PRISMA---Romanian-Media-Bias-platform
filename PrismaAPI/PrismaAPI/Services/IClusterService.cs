using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public interface IClusterService
{
    Task<PaginatedResultDto<ClusterListDto>> GetAllAsync(
        string? runId,
        bool? isEvent,
        int page = 1,
        int pageSize = 20,
        string sortBy = "articleCount",
        DateTime? dateFrom = null,
        DateTime? dateTo = null);

    Task<ClusterDetailDto?> GetDetailAsync(int runId, int clusterId);

    Task<ClusterSummaryDto?> GetSummaryAsync(int runId, int clusterId);
}
