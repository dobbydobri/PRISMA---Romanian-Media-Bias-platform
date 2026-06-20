namespace PrismaAPI.DTOs.FactCheck;

public record FactCheckBadgeDto(
    bool HasTier1Match,
    bool HasTier2Match,
    int FactCheckCount,
    int? MaxSeverity,
    List<FactCheckListItemDto> LinkedFactChecks
);
