using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc;
using PrismaAPI.DTOs;
using PrismaAPI.Services;

namespace PrismaAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class ConnectionsController : ControllerBase
{
    private readonly IConnectionsService _connectionsService;
    private readonly IConnectionsPathService _pathService;
    private readonly ILogger<ConnectionsController> _logger;

    public ConnectionsController(
        IConnectionsService connectionsService,
        IConnectionsPathService pathService,
        ILogger<ConnectionsController> logger)
    {
        _connectionsService = connectionsService;
        _pathService = pathService;
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

    [HttpGet("entities/{name}/articles")]
    [ProducesResponseType(typeof(List<EntityArticleDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<EntityArticleDto>>> GetEntityArticles(string name)
    {
        _logger.LogInformation("GET /api/connections/entities/{Name}/articles — Retrieving associated articles", name);
        var articles = await _connectionsService.GetEntityArticlesAsync(name);
        return Ok(articles);
    }

    [HttpGet("autocomplete")]
    [ProducesResponseType(typeof(List<EntitySuggestionDto>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<List<EntitySuggestionDto>>> Autocomplete(
        [FromQuery] string q,
        [FromQuery][Range(1, 100)] int limit = 20)
    {
        if (string.IsNullOrWhiteSpace(q) || q.Length < 2)
            return Ok(new List<EntitySuggestionDto>());

        _logger.LogInformation("GET /api/connections/autocomplete?q={Q}", q);
        var suggestions = await _pathService.AutocompleteAsync(q, limit);
        return Ok(suggestions);
    }

    [HttpGet("path")]
    [ProducesResponseType(typeof(EntityPathResponseDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status502BadGateway)]
    public async Task<ActionResult<EntityPathResponseDto>> FindPath(
        [FromQuery] string from,
        [FromQuery] string to)
    {
        if (string.IsNullOrWhiteSpace(from) || string.IsNullOrWhiteSpace(to))
            return BadRequest("Both 'from' and 'to' parameters are required.");

        if (from.Equals(to, StringComparison.OrdinalIgnoreCase))
            return BadRequest("'from' and 'to' must be different entities.");

        _logger.LogInformation("GET /api/connections/path?from={From}&to={To}", from, to);

        try
        {
            var result = await _pathService.FindPathAsync(from, to);
            if (result is null)
            {
                _logger.LogWarning("No connection found between {From} and {To}", from, to);
                return NotFound();
            }

            return Ok(result);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Graph service unreachable for path {From}→{To}", from, to);
            return StatusCode(StatusCodes.Status502BadGateway,
                new { error = "Graph service unavailable" });
        }
    }
}
