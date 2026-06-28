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

    public DbSet<ClusterCoverageMetric> ClusterCoverageMetrics => Set<ClusterCoverageMetric>();

    public DbSet<ClusterSummary> ClusterSummaries => Set<ClusterSummary>();

    public DbSet<FactCheck> FactChecks => Set<FactCheck>();

    public DbSet<FactCheckClusterMap> FactCheckClusterMaps => Set<FactCheckClusterMap>();

    public DbSet<EntityConnection> EntityConnections => Set<EntityConnection>();


    public PrismaDbContext(DbContextOptions<PrismaDbContext> options)
        : base(options)
    {
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
            entity.Property(a => a.LlmPromptVersion).HasColumnName("llm_prompt_version");
            entity.Property(a => a.LlmGovStance).HasColumnName("llm_gov_stance");
            entity.Property(a => a.LlmSovereignism).HasColumnName("llm_sovereignism");
            entity.Property(a => a.LlmConfidence).HasColumnName("llm_confidence");

            entity.Property(a => a.TfGovStance).HasColumnName("tf_gov_stance");
            entity.Property(a => a.TfGovStanceProb).HasColumnName("tf_gov_stance_prob").HasColumnType("jsonb");
            entity.Property(a => a.TfGovStanceConf).HasColumnName("tf_gov_stance_conf");
            entity.Property(a => a.TfFraming).HasColumnName("tf_framing");
            entity.Property(a => a.TfFramingProb).HasColumnName("tf_framing_prob").HasColumnType("jsonb");
            entity.Property(a => a.TfFramingConf).HasColumnName("tf_framing_conf");
            entity.Property(a => a.TfSovereignism).HasColumnName("tf_sovereignism");
            entity.Property(a => a.TfSovereignismProb).HasColumnName("tf_sovereignism_prob").HasColumnType("jsonb");
            entity.Property(a => a.TfSovereignismConf).HasColumnName("tf_sovereignism_conf");
            entity.Property(a => a.TfTopic).HasColumnName("tf_topic");
            entity.Property(a => a.TfTopicProb).HasColumnName("tf_topic_prob").HasColumnType("jsonb");
            entity.Property(a => a.TfTopicConf).HasColumnName("tf_topic_conf");

            entity.Property(a => a.IsExcluded).HasColumnName("is_excluded");
            entity.Property(a => a.IsTemplated).HasColumnName("is_templated");
            entity.Property(a => a.Fts).HasColumnName("fts").HasColumnType("tsvector");

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

        modelBuilder.Entity<ClusterCoverageMetric>(entity =>
        {
            entity.ToTable("cluster_coverage_metrics");

            entity.HasKey(c => new { c.ClusterRunId, c.ClusterId });

            entity.Property(c => c.ClusterRunId).HasColumnName("cluster_run_id");
            entity.Property(c => c.ClusterId).HasColumnName("cluster_id");
            entity.Property(c => c.ArticleCount).HasColumnName("article_count");
            entity.Property(c => c.OutletCount).HasColumnName("outlet_count");
            entity.Property(c => c.OutletTypeCount).HasColumnName("outlet_type_count");
            entity.Property(c => c.PopularityScore).HasColumnName("popularity_score");
            entity.Property(c => c.GapScore).HasColumnName("gap_score");
            entity.Property(c => c.Category).HasColumnName("category");
            entity.Property(c => c.CoveringOutlets).HasColumnName("covering_outlets").HasColumnType("jsonb");
            entity.Property(c => c.MissingOutlets).HasColumnName("missing_outlets").HasColumnType("jsonb");
            entity.Property(c => c.ComputedAt).HasColumnName("computed_at");
        });

        modelBuilder.Entity<ClusterSummary>(entity =>
        {
            entity.ToTable("cluster_summaries");

            entity.Property(cs => cs.Id).HasColumnName("id");
            entity.Property(cs => cs.Scope).HasColumnName("scope");
            entity.Property(cs => cs.ClusterRunId).HasColumnName("cluster_run_id");
            entity.Property(cs => cs.ClusterId).HasColumnName("cluster_id");
            entity.Property(cs => cs.SummaryText).HasColumnName("summary_text");
            entity.Property(cs => cs.KeyPoints)
                  .HasColumnName("key_points")
                  .HasColumnType("jsonb")
                  .HasConversion(
                      v => System.Text.Json.JsonSerializer.Serialize(v, (System.Text.Json.JsonSerializerOptions?)null),
                      v => System.Text.Json.JsonSerializer.Deserialize<List<string>>(v, (System.Text.Json.JsonSerializerOptions?)null));
            entity.Property(cs => cs.SourceArticleIds).HasColumnName("source_article_ids");
            entity.Property(cs => cs.Model).HasColumnName("model");
            entity.Property(cs => cs.PromptVersion).HasColumnName("prompt_version");
            entity.Property(cs => cs.MeanPairwiseCosine).HasColumnName("mean_pairwise_cosine");
            entity.Property(cs => cs.GenerationMs).HasColumnName("generation_ms");
            entity.Property(cs => cs.GeneratedAt).HasColumnName("generated_at");
            entity.Property(cs => cs.ClusterTitle).HasColumnName("cluster_title");

            entity.HasOne(cs => cs.ClusterRun)
                  .WithMany()
                  .HasForeignKey(cs => cs.ClusterRunId);
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
