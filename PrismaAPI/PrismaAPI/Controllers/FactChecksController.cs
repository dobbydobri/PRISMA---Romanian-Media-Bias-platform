using Microsoft.AspNetCore.Mvc;
using PrismaAPI.DTOs;
using PrismaAPI.DTOs.FactCheck;
using PrismaAPI.Services;

namespace PrismaAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class FactChecksController : ControllerBase
{
    private readonly FactCheckService _factCheckService;
    private readonly ILogger<FactChecksController> _logger;

    public FactChecksController(FactCheckService factCheckService, ILogger<FactChecksController> logger)
    {
        _factCheckService = factCheckService;
        _logger = logger;
    }

    [HttpGet]
    [ProducesResponseType(typeof(PaginatedResultDto<FactCheckListItemDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<PaginatedResultDto<FactCheckListItemDto>>> GetAll(
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20,
        [FromQuery] string? verdict = null,
        CancellationToken ct = default)
    {
        _logger.LogInformation(
            "GET /api/factchecks — verdict={Verdict}, page={Page}, pageSize={PageSize}",
            verdict, page, pageSize);

        if (page < 1) page = 1;
        if (pageSize is < 1 or > 100) pageSize = 20;
        var result = await _factCheckService.GetListAsync(page, pageSize, verdict, ct);
        return Ok(result);
    }

    [HttpGet("cluster/{runId}/{clusterId}")]
    [ProducesResponseType(typeof(List<FactCheckClusterDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<FactCheckClusterDto>>> GetByCluster(int runId, int clusterId)
    {
        _logger.LogInformation(
            "GET /api/factchecks/cluster/{RunId}/{ClusterId} — Retrieving Tier 1 fact checks",
            runId, clusterId);

        var matches = await _factCheckService.GetByClusterAsync(runId, clusterId);
        return Ok(matches);
    }

    [HttpGet("proximity")]
    [ProducesResponseType(typeof(List<FactCheckProximityDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<FactCheckProximityDto>>> GetProximity(
        [FromQuery] long articleId,
        [FromQuery] double threshold = 0.7,
        [FromQuery] int limit = 10)
    {
        _logger.LogInformation(
            "GET /api/factchecks/proximity — articleId={ArticleId}, threshold={Threshold}, limit={Limit}",
            articleId, threshold, limit);

        var results = await _factCheckService.GetProximityAsync(articleId, threshold, limit);
        return Ok(results);
    }

    [HttpGet("article/{id}")]
    [ProducesResponseType(typeof(List<FactCheckDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<FactCheckDto>>> GetByArticle(long id)
    {
        _logger.LogInformation("GET /api/factchecks/article/{Id} — Retrieving merged fact checks", id);

        var factChecks = await _factCheckService.GetByArticleAsync(id);
        return Ok(factChecks);
    }

    [HttpGet("badge/{clusterRunId:int}/{clusterId:int}")]
    [ProducesResponseType(typeof(FactCheckBadgeDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<FactCheckBadgeDto>> GetBadge(
        int clusterRunId,
        int clusterId,
        CancellationToken ct = default)
    {
        _logger.LogInformation(
            "GET /api/factchecks/badge/{ClusterRunId}/{ClusterId}",
            clusterRunId, clusterId);

        var result = await _factCheckService.GetBadgeForClusterAsync(clusterRunId, clusterId, ct);
        if (result is null) return NotFound();
        return Ok(result);
    }
}
