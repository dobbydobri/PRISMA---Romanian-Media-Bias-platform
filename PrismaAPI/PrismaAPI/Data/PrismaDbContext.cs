using Microsoft.EntityFrameworkCore;
using Pgvector.EntityFrameworkCore;
using PrismaAPI.Models;

namespace PrismaAPI.Data;

public class PrismaDbContext : DbContext
{

    public DbSet<Outlet> Outlets => Set<Outlet>();

    public DbSet<Article> Articles => Set<Article>();

    public DbSet<ArticleEntity> ArticleEntities => Set<ArticleEntity>();

    public DbSet<ArticleEntityFull> ArticleEntitiesFull => Set<ArticleEntityFull>();

    public DbSet<ClusterRun> ClusterRuns => Set<ClusterRun>();

    public DbSet<ClusterRunWindow> ClusterRunWindows => Set<ClusterRunWindow>();

    public DbSet<ClusterLabel> ClusterLabels => Set<ClusterLabel>();

    public DbSet<FactCheck> FactChecks => Set<FactCheck>();

    public DbSet<FactCheckClusterMap> FactCheckClusterMaps => Set<FactCheckClusterMap>();

    public DbSet<EntityConnection> EntityConnections => Set<EntityConnection>();


    public PrismaDbContext(DbContextOptions<PrismaDbContext> options)
        : base(options)
    {
        ChangeTracker.QueryTrackingBehavior = QueryTrackingBehavior.NoTracking;
    }


    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.HasPostgresExtension("vector");

        modelBuilder.Entity<Outlet>(entity =>
        {
            entity.ToTable("outlets");

            entity.Property(o => o.Id).HasColumnName("id");
            entity.Property(o => o.Name).HasColumnName("name");
            entity.Property(o => o.OutletType).HasColumnName("outlet_type");
            entity.Property(o => o.BaseUrl).HasColumnName("base_url");
            entity.Property(o => o.CreatedAt).HasColumnName("created_at");
        });

        modelBuilder.Entity<Article>(entity =>
        {
            entity.ToTable("articles");

            entity.Property(a => a.Id).HasColumnName("id");
            entity.Property(a => a.OutletId).HasColumnName("outlet_id");
            entity.Property(a => a.Url).HasColumnName("url");
            entity.Property(a => a.UrlHash).HasColumnName("url_hash");
            entity.Property(a => a.Title).HasColumnName("title");
            entity.Property(a => a.ContentText).HasColumnName("content_text");
            entity.Property(a => a.Authors).HasColumnName("authors")
                  .HasColumnType("text[]");
            entity.Property(a => a.PublishedAt).HasColumnName("published_at");
            entity.Property(a => a.QueueId).HasColumnName("queue_id");

            entity.Property(a => a.Embedding).HasColumnName("embedding")
                  .HasColumnType("vector(1024)");
            entity.Property(a => a.EmbeddedAt).HasColumnName("embedded_at");
            entity.Property(a => a.EmbeddingModel).HasColumnName("embedding_model");
            entity.Property(a => a.EmbeddingVersion).HasColumnName("embedding_version");

            entity.Property(a => a.ClusterRunId).HasColumnName("cluster_run_id");
            entity.Property(a => a.ClusterId).HasColumnName("cluster_id");
            entity.Property(a => a.SubClusterId).HasColumnName("sub_cluster_id");

            entity.Property(a => a.ScoreSensationalism).HasColumnName("score_sensationalism");
            entity.Property(a => a.ScoreCitationQuality).HasColumnName("score_citation_quality");
            entity.Property(a => a.ScoreRhetoricIntensity).HasColumnName("score_rhetoric_intensity");
            entity.Property(a => a.DiscourseRegisters).HasColumnName("discourse_registers")
                  .HasColumnType("jsonb");

            entity.Property(a => a.LlmCoalition).HasColumnName("llm_coalition");
            entity.Property(a => a.LlmEuAxis).HasColumnName("llm_eu_axis");
            entity.Property(a => a.LlmFraming).HasColumnName("llm_framing");
            entity.Property(a => a.LlmTopic).HasColumnName("llm_topic");
            entity.Property(a => a.LlmScoredAt).HasColumnName("llm_scored_at");

            entity.Property(a => a.PredIsPolitical).HasColumnName("pred_is_political");
            entity.Property(a => a.PredCoalition).HasColumnName("pred_coalition");
            entity.Property(a => a.PredEuAxis).HasColumnName("pred_eu_axis");
            entity.Property(a => a.PredScoredAt).HasColumnName("pred_scored_at");

            entity.HasOne(a => a.Outlet)
                  .WithMany(o => o.Articles)
                  .HasForeignKey(a => a.OutletId);

            entity.HasOne(a => a.ClusterRun)
                  .WithMany()
                  .HasForeignKey(a => a.ClusterRunId)
                  .IsRequired(false);
        });

        modelBuilder.Entity<ArticleEntity>(entity =>
        {
            entity.ToTable("article_entities");

            entity.Property(ae => ae.Id).HasColumnName("id");
            entity.Property(ae => ae.ArticleId).HasColumnName("article_id");
            entity.Property(ae => ae.EntityText).HasColumnName("entity_text");
            entity.Property(ae => ae.EntityLabel).HasColumnName("entity_label");
            entity.Property(ae => ae.CreatedAt).HasColumnName("created_at");

            entity.HasOne(ae => ae.Article)
                  .WithMany(a => a.ArticleEntities)
                  .HasForeignKey(ae => ae.ArticleId);
        });

        modelBuilder.Entity<ArticleEntityFull>(entity =>
        {
            entity.ToTable("article_entities_full");

            entity.Property(ef => ef.Id).HasColumnName("id");
            entity.Property(ef => ef.ArticleId).HasColumnName("article_id");
            entity.Property(ef => ef.EntityText).HasColumnName("entity_text");
            entity.Property(ef => ef.EntityLabel).HasColumnName("entity_label");
        });

        modelBuilder.Entity<ClusterRun>(entity =>
        {
            entity.ToTable("cluster_runs");

            entity.Property(cr => cr.Id).HasColumnName("id");
            entity.Property(cr => cr.CreatedAt).HasColumnName("created_at");
            entity.Property(cr => cr.CompletedAt).HasColumnName("completed_at");
            entity.Property(cr => cr.UmapNeighbors).HasColumnName("umap_neighbors");
            entity.Property(cr => cr.UmapComponents).HasColumnName("umap_components");
            entity.Property(cr => cr.TemporalScale).HasColumnName("temporal_scale");
            entity.Property(cr => cr.HdbscanMinSize).HasColumnName("hdbscan_min_size");
            entity.Property(cr => cr.HdbscanMinSamples).HasColumnName("hdbscan_min_samples");
            entity.Property(cr => cr.ClusterMethod).HasColumnName("cluster_method");
            entity.Property(cr => cr.WindowDays).HasColumnName("window_days");
            entity.Property(cr => cr.TotalClusters).HasColumnName("total_clusters");
            entity.Property(cr => cr.Notes).HasColumnName("notes");
        });

        modelBuilder.Entity<ClusterRunWindow>(entity =>
        {
            entity.ToTable("cluster_run_windows");

            entity.Property(w => w.Id).HasColumnName("id");
            entity.Property(w => w.RunId).HasColumnName("run_id");
            entity.Property(w => w.WindowStart).HasColumnName("window_start");
            entity.Property(w => w.WindowEnd).HasColumnName("window_end");
            entity.Property(w => w.ArticlesIn).HasColumnName("articles_in");
            entity.Property(w => w.NClusters).HasColumnName("n_clusters");
            entity.Property(w => w.NNoise).HasColumnName("n_noise");
            entity.Property(w => w.Dbcv).HasColumnName("dbcv");

            entity.HasOne(w => w.ClusterRun)
                  .WithMany(cr => cr.ClusterRunWindows)
                  .HasForeignKey(w => w.RunId);
        });

        modelBuilder.Entity<ClusterLabel>(entity =>
        {
            entity.ToTable("cluster_labels");

            entity.HasKey(cl => new { cl.ClusterRunId, cl.ClusterId });

            entity.Property(cl => cl.ClusterRunId).HasColumnName("cluster_run_id");
            entity.Property(cl => cl.ClusterId).HasColumnName("cluster_id");
            entity.Property(cl => cl.TopTfidfTerms).HasColumnName("top_tfidf_terms");
            entity.Property(cl => cl.TopEntities).HasColumnName("top_entities");
            entity.Property(cl => cl.LabelText).HasColumnName("label_text");
            entity.Property(cl => cl.ArticleCount).HasColumnName("article_count");
            entity.Property(cl => cl.OutletCount).HasColumnName("outlet_count");
            entity.Property(cl => cl.DateFrom).HasColumnName("date_from");
            entity.Property(cl => cl.DateTo).HasColumnName("date_to");
            entity.Property(cl => cl.CreatedAt).HasColumnName("created_at");
            entity.Property(cl => cl.ParentClusterId).HasColumnName("parent_cluster_id");
            entity.Property(cl => cl.IsEventCluster).HasColumnName("is_event_cluster");

            entity.HasOne(cl => cl.ClusterRun)
                  .WithMany(cr => cr.ClusterLabels)
                  .HasForeignKey(cl => cl.ClusterRunId);
        });

        modelBuilder.Entity<FactCheck>(entity =>
        {
            entity.ToTable("fact_checks");

            entity.Property(fc => fc.Id).HasColumnName("id");
            entity.Property(fc => fc.ArticleId).HasColumnName("article_id");
            entity.Property(fc => fc.OutletId).HasColumnName("outlet_id");
            entity.Property(fc => fc.Verdict).HasColumnName("verdict");
            entity.Property(fc => fc.VerdictType).HasColumnName("verdict_type");
            entity.Property(fc => fc.ClaimText).HasColumnName("claim_text");
            entity.Property(fc => fc.RawVerdict).HasColumnName("raw_verdict");
            entity.Property(fc => fc.PublishedAt).HasColumnName("published_at");
            entity.Property(fc => fc.CreatedAt).HasColumnName("created_at");

            entity.HasOne(fc => fc.Article)
                  .WithOne(a => a.FactCheck)
                  .HasForeignKey<FactCheck>(fc => fc.ArticleId);

            entity.HasOne(fc => fc.Outlet)
                  .WithMany(o => o.FactChecks)
                  .HasForeignKey(fc => fc.OutletId);
        });

        modelBuilder.Entity<FactCheckClusterMap>(entity =>
        {
            entity.ToTable("factcheck_cluster_map");

            entity.HasKey(m => new { m.FactcheckId, m.ArticleId, m.ClusterRunId, m.ClusterId });

            entity.Property(m => m.FactcheckId).HasColumnName("factcheck_id");
            entity.Property(m => m.ArticleId).HasColumnName("article_id");
            entity.Property(m => m.ClusterRunId).HasColumnName("cluster_run_id");
            entity.Property(m => m.ClusterId).HasColumnName("cluster_id");
            entity.Property(m => m.SubClusterId).HasColumnName("sub_cluster_id");
            entity.Property(m => m.Similarity).HasColumnName("similarity");
            entity.Property(m => m.SubSimilarity).HasColumnName("sub_similarity");
        });

        modelBuilder.Entity<EntityConnection>(entity =>
        {
            entity.ToTable("entity_connections");

            entity.Property(ec => ec.Id).HasColumnName("id");
            entity.Property(ec => ec.SourceEntity).HasColumnName("source_entity");
            entity.Property(ec => ec.SourceLabel).HasColumnName("source_label");
            entity.Property(ec => ec.TargetEntity).HasColumnName("target_entity");
            entity.Property(ec => ec.TargetLabel).HasColumnName("target_label");
            entity.Property(ec => ec.WeightRaw).HasColumnName("weight_raw");
            entity.Property(ec => ec.WeightPmi).HasColumnName("weight_pmi");
        });
    }
}
