using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public interface IConnectionsService
{
    Task<List<EntityConnectionDto>> GetEntityConnectionsAsync(string entityName, int limit = 50);
    Task<List<EntityArticleDto>> GetEntityArticlesAsync(string entityName);
}
