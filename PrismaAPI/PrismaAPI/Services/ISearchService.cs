using PrismaAPI.DTOs.Search;

namespace PrismaAPI.Services;

public interface ISearchService
{
    Task<SearchResponse> SearchArticlesAsync(SearchRequest request, CancellationToken ct);
}
