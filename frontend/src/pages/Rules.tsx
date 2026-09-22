import {
  Lightbulb, Plus, SlidersHorizontal,
  Trash2, Zap,
} from "lucide-react";
import * as React from "react";
import {
  api, type Rule, type RuleDraft, } from "@/lib/api";
import { urteilLabel } from "@/components/Urteil";
import { useAsync } from "@/lib/useEvents";
import {
  formatPrice, timeAgo,
} from "@/lib/utils";
import {
  Badge, Button, Card, EmptyState,
  Skeleton, Switch, } from "@/components/ui";
import { PageHeader } from "@/components/Layout";
import { useToast } from "@/components/Toast";
import { EMPTY_RULE, VORLAGEN } from "@/pages/regeln/vorlagen";
import { RuleEditor } from "@/pages/regeln/Editor";
import { Hygienekarte, TeilenKnopf, Vorschlaege } from "@/pages/regeln/Durchsicht";

export function Rules() {
  const toast = useToast();
  const { data: rules, loading, reload } = useAsync<Rule[]>(() => api.rules.list(), []);
  const [editing, setEditing] = React.useState<{ rule: RuleDraft; id?: number } | null>(null);

  const remove = async (rule: Rule) => {
    if (!window.confirm(`Regel „${rule.name}“ wirklich löschen?`)) return;
    try {
      await api.rules.remove(rule.id);
      toast.push("success", "Regel gelöscht", rule.name);
      reload();
    } catch (err) {
      toast.push("error", "Löschen fehlgeschlagen", (err as Error).message);
    }
  };

  const toggle = async (rule: Rule, enabled: boolean) => {
    try {
      await api.rules.update(rule.id, { ...toDraft(rule), enabled });
      reload();
    } catch (err) {
      toast.push("error", "Fehlgeschlagen", (err as Error).message);
    }
  };

  return (
    <>
      <PageHeader
        title="Regeln"
        description="Beim Bauen siehst du sofort, wie viele der letzten 500 Deals die Regel getroffen hätte — so tunst du sie rauschfrei."
        action={
          <div className="flex gap-2">
            <TeilenKnopf onFertig={reload} />
            <Button onClick={() => setEditing({ rule: { ...EMPTY_RULE } })}>
              <Plus className="h-4 w-4" />
              Neue Regel
            </Button>
          </div>
        }
      />

      <Vorschlaege onUebernehmen={(regel) =>
        setEditing({ rule: { ...EMPTY_RULE, ...regel } as RuleDraft })} />

      <Hygienekarte onBearbeiten={(id) => {
        const regel = rules?.find((r) => r.id === id);
        if (regel) setEditing({ rule: toDraft(regel), id });
      }} />

      <Card className="mb-6 p-4">
        <p className="mb-2.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Vorlagen — ein Klick, dann anpassen
        </p>
        <div className="flex flex-wrap gap-2">
          {VORLAGEN.map((vorlage) => (
            <button
              key={vorlage.name}
              type="button"
              title={vorlage.beschreibung}
              onClick={() => setEditing({
                rule: { ...EMPTY_RULE, ...vorlage.regel } as RuleDraft,
              })}
              className="rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
            >
              <Lightbulb className="mr-1 inline h-3 w-3" />
              {vorlage.name}
            </button>
          ))}
        </div>
      </Card>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40" />)}
        </div>
      ) : !rules?.length ? (
        <Card>
          <EmptyState
            icon={<SlidersHorizontal className="h-9 w-9" />}
            title="Noch keine Regeln"
            description="Ohne Regel wird nichts verschickt — gesammelt wird trotzdem. Fang mit „alles was gratis ist“ an."
            action={
              <Button onClick={() => setEditing({
                rule: { ...EMPTY_RULE, name: "Alles Gratis", nur_gratis: true,
                        priority: "SOFORT" },
              })}>
                <Plus className="h-4 w-4" />
                Erste Regel anlegen
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {rules.map((rule) => (
            <Card key={rule.id} hover className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate font-semibold">{rule.name}</h3>
                    {rule.priority === "SOFORT" && (
                      <Badge variant="warning">
                        <Zap className="h-3 w-3" />
                        SOFORT
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {rule.match_count} Treffer
                    {rule.last_match && ` · zuletzt ${timeAgo(rule.last_match)}`}
                  </p>
                </div>
                <Switch checked={rule.enabled} onChange={(v) => toggle(rule, v)}
                  label={`${rule.name} ein-/ausschalten`} />
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {rule.nur_gratis && <Badge variant="success">nur gratis</Badge>}
                {rule.erwachsen && <Badge variant="outline">18+</Badge>}
                {rule.max_preis != null && <Badge variant="outline">≤ {formatPrice(rule.max_preis)}</Badge>}
                {rule.min_rabatt_prozent != null && (
                  <Badge variant="outline">≥ {rule.min_rabatt_prozent}% Rabatt</Badge>
                )}
                {rule.min_temperatur != null && (
                  <Badge variant="outline">≥ {rule.min_temperatur}°</Badge>
                )}
                {rule.min_urteil && (
                  <Badge variant="default">≥ {urteilLabel(rule.min_urteil)}</Badge>
                )}
                {rule.min_fehler_score ? (
                  <Badge variant="signal">
                    Preisfehler ≥ {rule.min_fehler_score}
                  </Badge>
                ) : null}
                {rule.keywords.slice(0, 3).map((keyword) => (
                  <Badge key={keyword}>{keyword}</Badge>
                ))}
                {rule.keywords.length > 3 && (
                  <Badge variant="outline">+{rule.keywords.length - 3}</Badge>
                )}
                {rule.channels.length === 0 && (
                  <Badge variant="destructive" title="Ohne Kanal wird nichts zugestellt">
                    kein Kanal
                  </Badge>
                )}
              </div>

              <div className="mt-4 flex gap-2">
                <Button variant="outline" size="sm"
                  onClick={() => setEditing({ rule: toDraft(rule), id: rule.id })}>
                  Bearbeiten
                </Button>
                <Button variant="ghost" size="sm" onClick={() => remove(rule)}
                  aria-label="Regel löschen">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <RuleEditor
          initial={editing.rule}
          ruleId={editing.id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </>
  );
}

const toDraft = (rule: Rule): RuleDraft => ({
  name: rule.name,
  enabled: rule.enabled,
  priority: rule.priority,
  keywords: rule.keywords,
  required_keywords: rule.required_keywords,
  blacklist: rule.blacklist,
  max_preis: rule.max_preis,
  min_rabatt_prozent: rule.min_rabatt_prozent,
  nur_gratis: rule.nur_gratis,
  erwachsen: Boolean(rule.erwachsen),
  min_temperatur: rule.min_temperatur,
  min_urteil: rule.min_urteil,
  min_fehler_score: rule.min_fehler_score,
  sources: rule.sources,
  kategorien: rule.kategorien,
  warengruppen: rule.warengruppen ?? [],
  haendler: rule.haendler,
  channels: rule.channels,
});
