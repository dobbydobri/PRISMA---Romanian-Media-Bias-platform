using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("cluster_runs")]
public class ClusterRun
{
    [Key]
    [Column("id")]
    public int Id { get; set; }

    [Column("created_at")]
    public DateTime? CreatedAt { get; set; }

    [Column("completed_at")]
    public DateTime? CompletedAt { get; set; }


    [Column("umap_neighbors")]
    public int? UmapNeighbors { get; set; }

    [Column("umap_components")]
    public int? UmapComponents { get; set; }

    [Column("temporal_scale")]
    public double? TemporalScale { get; set; }


    [Column("hdbscan_min_size")]
    public int? HdbscanMinSize { get; set; }

    [Column("hdbscan_min_samples")]
    public int? HdbscanMinSamples { get; set; }

    [Column("cluster_method")]
    public string? ClusterMethod { get; set; }


    [Column("window_days")]
    public int? WindowDays { get; set; }

    [Column("total_clusters")]
    public int? TotalClusters { get; set; }

    [Column("notes")]
    public string? Notes { get; set; }


    public ICollection<ClusterLabel> ClusterLabels { get; set; } = new List<ClusterLabel>();

    public ICollection<ClusterRunWindow> ClusterRunWindows { get; set; } = new List<ClusterRunWindow>();
}
