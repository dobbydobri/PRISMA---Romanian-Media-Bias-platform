using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("cluster_run_windows")]
public class ClusterRunWindow
{
    [Key]
    [Column("id")]
    public int Id { get; set; }

    [Column("run_id")]
    public int RunId { get; set; }

    [Column("window_start")]
    public DateOnly WindowStart { get; set; }

    [Column("window_end")]
    public DateOnly WindowEnd { get; set; }

    [Column("articles_in")]
    public int ArticlesIn { get; set; }

    [Column("n_clusters")]
    public int NClusters { get; set; }

    [Column("n_noise")]
    public int NNoise { get; set; }

    [Column("dbcv")]
    public double? Dbcv { get; set; }


    public ClusterRun ClusterRun { get; set; } = null!;
}
