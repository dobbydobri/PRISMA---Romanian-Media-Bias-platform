using Microsoft.AspNetCore.Mvc;
using PrismaAPI.DTOs.Search;
using PrismaAPI.Services;

namespace PrismaAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class SearchController : ControllerBase
{
    private readonly ISearchService _searchService;
    private readonly ILogger<SearchController> _logger;

    public SearchController(ISearchService searchService, ILogger<SearchController> logger)
    {
        _searchService = searchService;
        _logger = logger;
    }

    [HttpPost]
    [ProducesResponseType(typeof(SearchResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status502BadGateway)]
    public async Task<IActionResult> Search(
        [FromBody] SearchRequest request,
        CancellationToken ct)
    {
        if (!ModelState.IsValid)
            return BadRequest(ModelState);

        _logger.LogInformation(
            "POST /api/search — query={Query}, top_k={TopK}",
            request.Query, request.TopK);

        try
        {
            var result = await _searchService.SearchArticlesAsync(request, ct);
            return Ok(result);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "Query embedder unreachable or returned an error");
            return StatusCode(StatusCodes.Status502BadGateway,
                new { error = "Search embedder unavailable" });
        }
        catch (InvalidOperationException ex) when (ex.Message.Contains("Embedder"))
        {
            _logger.LogError(ex, "Query embedder returned an invalid vector");
            return StatusCode(StatusCodes.Status502BadGateway,
                new { error = "Search embedder returned invalid response" });
        }
    }
}
