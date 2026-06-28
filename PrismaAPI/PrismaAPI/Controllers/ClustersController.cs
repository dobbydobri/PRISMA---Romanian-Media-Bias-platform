using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc;
using PrismaAPI.DTOs;
using PrismaAPI.Services;

namespace PrismaAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class ClustersController : ControllerBase
{
    private readonly IClusterService _clusterService;
    private readonly IClusterRunWindowService _clusterRunWindowService;
    private readonly ILogger<ClustersController> _logger;

    public ClustersController(
        IClusterService clusterService,
        IClusterRunWindowService clusterRunWindowService,
        ILogger<ClustersController> logger)
    {
        _clusterService = clusterService;
        _clusterRunWindowService = clusterRunWindowService;
        _logger = logger;
    }

    [HttpGet]
    [ProducesResponseType(typeof(PaginatedResultDto<ClusterListDto>), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<PaginatedResultDto<ClusterListDto>>> GetAll(
        [FromQuery] string? runId,
        [FromQuery] bool? isEvent,
        [FromQuery][Range(1, int.MaxValue)] int page = 1,
        [FromQuery][Range(1, 100)] int pageSize = 20,
        [FromQuery] string sortBy = "articleCount",
        [FromQuery] DateTime? dateFrom = null,
        [FromQuery] DateTime? dateTo = null)
    {
        _logger.LogInformation(
            "GET /api/clusters — runId={RunId}, isEvent={IsEvent}, page={Page}, pageSize={PageSize}, sortBy={SortBy}, dateFrom={DateFrom}, dateTo={DateTo}",
            runId, isEvent, page, pageSize, sortBy, dateFrom, dateTo);

        var result = await _clusterService.GetAllAsync(runId, isEvent, page, pageSize, sortBy, dateFrom, dateTo);
        return Ok(result);
    }

    [HttpGet("{runId}/{clusterId}")]
    [ProducesResponseType(typeof(ClusterDetailDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ClusterDetailDto>> GetDetail(int runId, int clusterId)
    {
        _logger.LogInformation(
            "GET /api/clusters/{RunId}/{ClusterId} — Retrieving cluster detail",
            runId, clusterId);

        var detail = await _clusterService.GetDetailAsync(runId, clusterId);
        if (detail is null)
        {
            _logger.LogWarning("Cluster run={RunId}, cluster={ClusterId} not found", runId, clusterId);
            return NotFound();
        }

        return Ok(detail);
    }

    [HttpGet("{runId}/{clusterId}/summary")]
    [ProducesResponseType(typeof(ClusterSummaryDto), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ClusterSummaryDto>> GetSummary(int runId, int clusterId)
    {
        _logger.LogInformation(
            "GET /api/clusters/{RunId}/{ClusterId}/summary — Retrieving cluster summary",
            runId, clusterId);

        var summary = await _clusterService.GetSummaryAsync(runId, clusterId);
        if (summary is null)
        {
            _logger.LogWarning("Cluster summary run={RunId}, cluster={ClusterId} not found", runId, clusterId);
            return NotFound();
        }

        return Ok(summary);
    }

    [HttpGet("windows")]
    [ProducesResponseType(typeof(List<ClusterRunWindowDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<ClusterRunWindowDto>>> GetWindows([FromQuery] int? runId)
    {
        _logger.LogInformation("GET /api/clusters/windows — runId={RunId}", runId);

        var windows = runId.HasValue
            ? await _clusterRunWindowService.GetByRunIdAsync(runId.Value)
            : await _clusterRunWindowService.GetLatestAsync();
        return Ok(windows);
    }
}
