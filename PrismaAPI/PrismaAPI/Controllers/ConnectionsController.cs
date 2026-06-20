using Microsoft.AspNetCore.Mvc;
using PrismaAPI.DTOs;
using PrismaAPI.Services;

namespace PrismaAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class ConnectionsController : ControllerBase
{
    private readonly ConnectionsService _connectionsService;
    private readonly ILogger<ConnectionsController> _logger;

    public ConnectionsController(ConnectionsService connectionsService, ILogger<ConnectionsController> logger)
    {
        _connectionsService = connectionsService;
        _logger = logger;
    }

    [HttpGet("entities/{name}")]
    [ProducesResponseType(typeof(List<EntityConnectionDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<EntityConnectionDto>>> GetEntityConnections(string name)
    {
        _logger.LogInformation("GET /api/connections/entities/{Name} — Retrieving co-mentioned entities", name);

        var connections = await _connectionsService.GetEntityConnectionsAsync(name);
        return Ok(connections);
    }

    [HttpGet("path")]
    [ProducesResponseType(typeof(EntityPathDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<EntityPathDto>> FindPath(
        [FromQuery] string from,
        [FromQuery] string to)
    {
        _logger.LogInformation(
            "GET /api/connections/path — from={From}, to={To}",
            from, to);

        var path = await _connectionsService.FindPathAsync(from, to);
        if (path is null)
        {
            _logger.LogWarning("No path found between {From} and {To}", from, to);
            return NotFound();
        }

        return Ok(path);
    }

    [HttpGet("entities/{name}/articles")]
    [ProducesResponseType(typeof(List<EntityArticleDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<EntityArticleDto>>> GetEntityArticles(string name)
    {
        _logger.LogInformation(
            "GET /api/connections/entities/{Name}/articles — Retrieving associated articles",
            name);

        var articles = await _connectionsService.GetEntityArticlesAsync(name);
        return Ok(articles);
    }
}
