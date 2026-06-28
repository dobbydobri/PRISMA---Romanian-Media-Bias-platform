using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public interface IConnectionsPathService
{
    Task<List<EntitySuggestionDto>> AutocompleteAsync(string query, int limit = 20);
    Task<EntityPathResponseDto?> FindPathAsync(string entityA, string entityB);
}
