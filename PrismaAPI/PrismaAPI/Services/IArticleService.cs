using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public interface IArticleService
{
    Task<PaginatedResultDto<ArticleListDto>> GetAllAsync(
        int? outletId,
        string? topic,
        string? framing,
        int page = 1,
        int pageSize = 20);

    Task<ArticleDetailDto?> GetByIdAsync(long id);
}
