using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public interface IAnalysisService
{
    Task<List<BiasChartPointDto>> GetBiasChartAsync();
    Task<List<ScoresComparisonDto>> GetScoresComparisonAsync();
    Task<List<TopicDistributionDto>> GetTopicDistributionAsync();
    Task<List<FramingDistributionDto>> GetFramingDistributionAsync();
    Task<List<CoverageGapDto>> GetCoverageGapsAsync(int? runId);
    Task<PaginatedResultDto<LlmVsXgboostDto>> GetLlmVsXgboostAsync(int? outletId, int page = 1, int pageSize = 20);
}
