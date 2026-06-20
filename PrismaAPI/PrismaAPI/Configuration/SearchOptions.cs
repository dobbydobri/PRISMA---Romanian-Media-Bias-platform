namespace PrismaAPI.Configuration;

public class SearchOptions
{
    public const string Section = "Search";

    public string EmbedderBaseUrl { get; set; } = "http://query_embedder:8081";

    public int EmbedderTimeoutMs { get; set; } = 5000;

    public int CandidatesPerLeg { get; set; } = 50;

    public double RrfK { get; set; } = 60.0;

    public double CosSimFloor { get; set; } = 0.70;

    public int DefaultTopK { get; set; } = 10;

    public int MaxTopK { get; set; } = 50;

    public int HnswEfSearch { get; set; } = 200;
}
