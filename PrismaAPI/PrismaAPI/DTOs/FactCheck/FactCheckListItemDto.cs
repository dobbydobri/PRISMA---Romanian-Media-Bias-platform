namespace PrismaAPI.DTOs.FactCheck;

public record FactCheckListItemDto(
    long Id,
    long ArticleId,
    string Title,
    string OutletName,
    string Verdict,
    string VerdictType,
    int? SeverityScore,
    DateTime PublishedAt,
    string? Url
);
