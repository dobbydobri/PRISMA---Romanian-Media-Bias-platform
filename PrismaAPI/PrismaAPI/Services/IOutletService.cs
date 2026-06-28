using PrismaAPI.DTOs;

namespace PrismaAPI.Services;

public interface IOutletService
{
    Task<List<OutletSummaryDto>> GetAllAsync();
}
