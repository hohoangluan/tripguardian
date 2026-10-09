-- Weekly groups of after-trip notes and free-text wishes (docs/ANALYTICS.md §Insights), made by `python -m analytics cluster`.
CREATE TABLE insight_clusters (
    id bigserial PRIMARY KEY,
    week date NOT NULL,
    source text NOT NULL CHECK (source IN ('feedback', 'free_text')),
    label text NOT NULL,
    size integer NOT NULL,
    examples jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX insight_clusters_week ON insight_clusters (week DESC);
