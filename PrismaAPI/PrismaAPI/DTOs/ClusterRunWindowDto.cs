namespace PrismaAPI.DTOs;

public class ClusterRunWindowDto
{
    public int Id { get; set; }

    public int RunId { get; set; }

    public DateOnly WindowStart { get; set; }

    public DateOnly WindowEnd { get; set; }

    public int ArticlesIn { get; set; }

    public int NClusters { get; set; }

    public int NNoise { get; set; }

    public double? Dbcv { get; set; }
}
