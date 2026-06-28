using Microsoft.AspNetCore.Mvc;
using PrismaAPI.DTOs;
using PrismaAPI.Services;

namespace PrismaAPI.Controllers;

[ApiController]
[Route("api/[controller]")]
[Produces("application/json")]
public class OutletsController : ControllerBase
{
    private readonly IOutletService _outletService;
    private readonly ILogger<OutletsController> _logger;

    public OutletsController(IOutletService outletService, ILogger<OutletsController> logger)
    {
        _outletService = outletService;
        _logger = logger;
    }

    [HttpGet]
    [ProducesResponseType(typeof(List<OutletSummaryDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<OutletSummaryDto>>> GetAll()
    {
        _logger.LogInformation("GET /api/outlets — Retrieving all outlets with aggregated statistics");

        var outlets = await _outletService.GetAllAsync();
        return Ok(outlets);
    }
}
