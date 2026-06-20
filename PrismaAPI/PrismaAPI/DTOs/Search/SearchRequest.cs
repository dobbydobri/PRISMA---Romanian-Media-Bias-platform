using System.ComponentModel.DataAnnotations;

namespace PrismaAPI.DTOs.Search;

public class SearchRequest
{
    [Required]
    [StringLength(512, MinimumLength = 1)]
    public string Query { get; set; } = null!;

    public int? TopK { get; set; }

    public SearchFilters? Filters { get; set; }
}

public class SearchFilters
{
    public int[]? OutletIds { get; set; }

    public DateOnly? DateFrom { get; set; }

    public DateOnly? DateTo { get; set; }

    public bool? IsFactCheck { get; set; }
}
