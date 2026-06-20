namespace PrismaAPI.DTOs;

public class SearchResultDto
{
    public long Id { get; set; }

    public string Title { get; set; } = string.Empty;

    public string? OutletName { get; set; }

    public DateTime? PublishedAt { get; set; }

    public double Similarity { get; set; }
}
