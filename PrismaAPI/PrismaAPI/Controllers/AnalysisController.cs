using Microsoft.AspNetCore.Mvc;
using PrismaAPI.DTOs;
using PrismaAPI.Services;

namespace PrismaAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class AnalysisController : ControllerBase
{
    private readonly AnalysisService _analysisService;
    private readonly ILogger<AnalysisController> _logger;

    public AnalysisController(AnalysisService analysisService, ILogger<AnalysisController> logger)
    {
        _analysisService = analysisService;
        _logger = logger;
    }

    [HttpGet("bias-chart")]
    [ProducesResponseType(typeof(List<BiasChartPointDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<BiasChartPointDto>>> GetBiasChart()
    {
        _logger.LogInformation("GET /api/analysis/bias-chart — Retrieving bias chart data");

        var points = await _analysisService.GetBiasChartAsync();
        return Ok(points);
    }

    [HttpGet("scores-comparison")]
    [ProducesResponseType(typeof(List<ScoresComparisonDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<ScoresComparisonDto>>> GetScoresComparison()
    {
        _logger.LogInformation("GET /api/analysis/scores-comparison — Retrieving score comparisons");

        var scores = await _analysisService.GetScoresComparisonAsync();
        return Ok(scores);
    }

    [HttpGet("topic-distribution")]
    [ProducesResponseType(typeof(List<TopicDistributionDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<TopicDistributionDto>>> GetTopicDistribution()
    {
        _logger.LogInformation("GET /api/analysis/topic-distribution — Retrieving topic distributions");

        var distributions = await _analysisService.GetTopicDistributionAsync();
        return Ok(distributions);
    }

    [HttpGet("framing-distribution")]
    [ProducesResponseType(typeof(List<FramingDistributionDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<FramingDistributionDto>>> GetFramingDistribution()
    {
        _logger.LogInformation("GET /api/analysis/framing-distribution — Retrieving framing distributions");

        var distributions = await _analysisService.GetFramingDistributionAsync();
        return Ok(distributions);
    }

    [HttpGet("coverage-gaps")]
    [ProducesResponseType(typeof(List<CoverageGapDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<CoverageGapDto>>> GetCoverageGaps([FromQuery] int? runId)
    {
        _logger.LogInformation("GET /api/analysis/coverage-gaps — runId={RunId}", runId);

        var gaps = await _analysisService.GetCoverageGapsAsync(runId);
        return Ok(gaps);
    }

    [HttpGet("llm-vs-xgboost")]
    [ProducesResponseType(typeof(PaginatedResultDto<LlmVsXgboostDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<PaginatedResultDto<LlmVsXgboostDto>>> GetLlmVsXgboost(
        [FromQuery] int? outletId,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20)
    {
        _logger.LogInformation(
            "GET /api/analysis/llm-vs-xgboost — outletId={OutletId}, page={Page}, pageSize={PageSize}",
            outletId, page, pageSize);

        var result = await _analysisService.GetLlmVsXgboostAsync(outletId, page, pageSize);
        return Ok(result);
    }
}
