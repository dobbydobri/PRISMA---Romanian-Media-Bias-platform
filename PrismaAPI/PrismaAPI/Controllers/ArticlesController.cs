using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc;
using PrismaAPI.DTOs;
using PrismaAPI.Services;

namespace PrismaAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class ArticlesController : ControllerBase
{
    private readonly IArticleService _articleService;
    private readonly ILogger<ArticlesController> _logger;

    public ArticlesController(IArticleService articleService, ILogger<ArticlesController> logger)
    {
        _articleService = articleService;
        _logger = logger;
    }

    [HttpGet]
    [ProducesResponseType(typeof(PaginatedResultDto<ArticleListDto>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<PaginatedResultDto<ArticleListDto>>> GetAll(
        [FromQuery] int? outletId,
        [FromQuery] string? topic,
        [FromQuery] string? framing,
        [FromQuery][Range(1, int.MaxValue)] int page = 1,
        [FromQuery][Range(1, 100)] int pageSize = 20)
    {
        _logger.LogInformation(
            "GET /api/articles — outletId={OutletId}, topic={Topic}, framing={Framing}, page={Page}, pageSize={PageSize}",
            outletId, topic, framing, page, pageSize);

        var result = await _articleService.GetAllAsync(outletId, topic, framing, page, pageSize);
        return Ok(result);
    }

    [HttpGet("{id}")]
    [ProducesResponseType(typeof(ArticleDetailDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ArticleDetailDto>> GetById(long id)
    {
        _logger.LogInformation("GET /api/articles/{Id} — Retrieving article detail", id);

        var article = await _articleService.GetByIdAsync(id);
        if (article is null)
        {
            _logger.LogWarning("Article {Id} not found", id);
            return NotFound();
        }

        return Ok(article);
    }
}
