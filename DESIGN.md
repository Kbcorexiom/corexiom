<!--
Copyright 2026 Karim Benrezzag <Karim.benrezzag@corexiom.com>
SPDX-License-Identifier: Apache-2.0
-->

# Corexiom v2 — Conception du noyau

Refonte du noyau de raisonnement selon deux principes : **hybrider** (le
neuronal peuple, le symbolique vérifie) et **fonder** (remplacer les
heuristiques par une sémantique définie, avec des garanties explicites).

Ce document distingue scrupuleusement ce qui est **prouvé par construction**,
ce qui est **garanti**, et ce qui est seulement **validé empiriquement**. C'est
le cœur de l'honnêteté du projet : on ne revendique pas une solidité qu'on n'a
pas démontrée.

---

## 1. Modèle

Le monde est un ensemble d'**assertions** atomiques, chacune portant un *degré
de croyance* `bel ∈ [0, 1]`. On distingue deux statuts :

- **Axiome** (`Status.AXIOM`) : croyance verrouillée à `1.0`, **inviolable**.
  C'est une contrainte dure. Le violer = incohérence dure (prouvable).
- **Croyance** (`Status.BELIEF`) : degré révisable dans `[0, 1]`, partant d'un
  *a priori* `prior`.

Les assertions sont reliées par des **liens** typés (`Relation`) :

| Relation | Sémantique | Effet sur la propagation |
|---|---|---|
| `IMPLIES(a→b, w)` | si `a` alors `b` | augmente la cible de `b` |
| `SUPPORTS(a→b, w)` | `a` est une évidence pour `b` | augmente la cible de `b` (plus faible) |
| `CONTRADICTS(a,b,w)` | `a` et `b` ne peuvent être vrais ensemble | diminue la cible de chacun ; conflit |

`CONTRADICTS` est symétrique (enregistré dans les deux sens).

Toute conclusion du moteur s'accompagne d'une **justification** (`Justification`)
listant les assertions et liens qui la fondent : c'est l'explicabilité native.

---

## 2. Sémantique de la propagation

Soit `bel_k` l'état (vecteur des croyances) à l'itération `k`. Pour chaque
assertion non-axiome `a` de prior `p_a` :

```
support(a)  = Σ  bel_k[s] · w      sur les liens (s → a) de type IMPLIES ou SUPPORTS
conflict(a) = Σ  bel_k[c] · w      sur les liens (c — a) de type CONTRADICTS
target(a)   = clamp( p_a + G⁺·support(a) − G⁻·conflict(a) , 0, 1 )
bel_{k+1}[a] = (1 − λ)·bel_k[a] + λ·target(a)          avec λ ∈ (0, 1]
```

Pour les axiomes : `bel_{k+1} = bel_k = 1.0`.

**Paramètres de la dynamique** (fixés au constructeur de `ReasoningEngine`,
tous configurables, valeurs par défaut sûres et amorties) :

| Paramètre | Symbole | Défaut | Rôle |
|---|---|---|---|
| `gain_support`  | G⁺ | `0.6`   | poids des évidences (`IMPLIES`/`SUPPORTS`) sur la cible |
| `gain_conflict` | G⁻ | `0.8`   | poids des contradictions (`CONTRADICTS`) sur la cible |
| `relax`         | λ  | `0.5`   | amortissement de la mise à jour, dans `(0, 1]` |
| `epsilon`       | ε  | `1e-9`  | seuil de détection du point fixe |
| `max_iters`     | —  | `1000`  | plafond d'itérations (terminaison) |

Le choix `G⁻ > G⁺` (0.8 > 0.6) est **délibéré** : le moteur pèse davantage le
conflit que le soutien. C'est une **prudence par conception** — face au doute, il
dégrade une croyance plutôt que de la gonfler. C'est la traduction numérique du
principe « suspendre plutôt qu'halluciner ». Le ratio G⁻/G⁺ règle la
« personnalité » du moteur (plus prudent si on l'augmente).

**Mise à jour synchrone (Jacobi)** : toutes les cibles sont calculées à partir
du **même** instantané `bel_k`. C'est ce qui donne l'indépendance à l'ordre.

On itère jusqu'à `max_k |bel_{k+1} − bel_k| < ε` (point fixe atteint) ou jusqu'à
`max_iters` (terminaison garantie).

### Garanties

| Propriété | Statut | Justification |
|---|---|---|
| **Bornes** `bel ∈ [0,1]` | ✅ prouvé | `clamp` à chaque étape ; init dans `[0,1]` |
| **Préservation des axiomes** | ✅ prouvé | les axiomes ne sont jamais mis à jour |
| **Déterminisme** | ✅ prouvé | aucune source d'aléa |
| **Indépendance à l'ordre** | ✅ prouvé | mise à jour synchrone depuis `bel_k` |
| **Terminaison** | ✅ garanti | plafond `max_iters` |
| **Convergence vers un point fixe** | 🔬 validé | relaxation `λ<1` (amortissement) ; vérifié sur des milliers de graphes générés aléatoirement (tests de propriété) |

> Honnêteté : nous **ne revendiquons pas** une preuve analytique de convergence
> universelle pour tout graphe. Nous garantissons la *terminaison* et démontrons
> *empiriquement* (property-based testing) qu'à l'arrêt, l'état est un
> quasi-point-fixe (réappliquer l'opérateur le déplace de moins de `ε`).

> **Régime de convergence (mesuré).** La convergence n'est observée de façon
> fiable qu'en **régime amorti** (λ ≲ 0.5, le défaut). À λ ≥ 0.8, sur des graphes
> à contradictions fortes, l'opérateur peut **osciller** et atteindre le plafond
> `max_iters` sans point fixe — **sans jamais violer la terminaison ni les bornes
> `[0, 1]`**. Autrement dit : l'amortissement est ce qui *achète* la convergence.
> La borne supérieure `λ = 1` reste autorisée mais déconseillée pour cette raison.

---

## 3. Cohérence

- **Cohérence dure** (`bool`) — décidable exactement. `False` s'il existe un lien
  `CONTRADICTS` entre **deux axiomes** : deux propositions inviolables et
  mutuellement exclusives ne peuvent coexister. La preuve est l'paire d'axiomes
  et le lien.
- **Score de cohérence molle** ∈ `[0,1]` :

```
conflict_mass = Σ  bel[a]·bel[b]·w   sur les liens CONTRADICTS (comptés une fois)
coherence     = 1 − clamp( conflict_mass / Σw , 0, 1 )
```

Borné par construction : `0 ≤ coherence ≤ 1` (prouvé).

---

## 4. Décision et suspension (fondées)

`decide(threshold θ, margin δ)` choisit l'assertion **actionnable** de plus
haute croyance `≥ θ`, sauf suspension. Règles de suspension, dans l'ordre,
chacune renvoyant une justification :

- **S1 — `AXIOM_CONFLICT`** : incohérence dure détectée. On ne décide pas sur un
  socle contradictoire.
- **S2 — `VIOLATES_AXIOM`** : une action en `CONTRADICTS` direct avec un axiome
  est **structurellement écartée** des candidates (la retenir violerait une
  contrainte inviolable). Ce verdict n'est rendu que s'il **ne reste aucune
  action autorisée viable** *et* qu'une action sérieuse (a priori `≥ θ`) a été
  ainsi écartée : s'il existe une option permise au-dessus du seuil, le moteur
  la préfère (cf. `test_allowed_preferred_over_forbidden`).
- **S3 — `AMBIGUOUS`** : `bel(top₁) − bel(top₂) < δ`. Le système ne tranche pas
  un quasi-ex æquo : il suspend plutôt que d'inventer une préférence.
- Sinon **`DECIDED`** : `top₁`, avec sa justification (chaîne de support).
- Aucune candidate `≥ θ` → **`INSUFFICIENT_BELIEF`** (pas de décision forcée).

> **Préséance réelle.** L'exclusion d'une action interdite est un *fait
> structurel*, appliqué **avant** le choix parmi les candidates : une action
> contredisant un axiome n'est jamais retenue, quelle que soit sa croyance. La
> hiérarchie effective est donc : `AXIOM_CONFLICT` (socle) → exclusion des
> actions interdites → `AMBIGUOUS`/`DECIDED` parmi les autorisées →
> `VIOLATES_AXIOM` (si une action sérieuse a été écartée et qu'il ne reste rien
> d'autorisé) → `INSUFFICIENT_BELIEF`.

> **Indépendance au poids.** L'interdiction dépend de l'**existence** d'un lien
> `CONTRADICTS` vers un axiome, **pas de son poids** : même un poids minime
> interdit l'action. Le poids d'un lien `CONTRADICTS` n'agit que sur la
> propagation (§2) et le score de cohérence molle (§3) ; face à un axiome, la
> contrainte est *dure*, donc binaire.

C'est la matérialisation du principe fondateur : *suspendre plutôt
qu'halluciner*, mais sur des critères explicites et traçables.

---

## 5. Hybridation : perception enfichable

```
Perceiver (protocole)
 ├─ RuleBasedPerceiver   — extraction par motifs (par défaut, sans dépendance)
 └─ LLMPerceiver         — interface pour un modèle neuronal (peuple le graphe)
```

Le moteur ne dépend **pas** de la façon dont les assertions sont produites. Un
LLM peut transformer du langage naturel en assertions structurées (le neuronal
*propose*) ; le moteur les *vérifie*, détecte les contradictions, et suspend si
besoin (le symbolique *contraint*). Le neuronal n'a jamais le dernier mot sur la
cohérence.

---

## 6. Ce que ce noyau n'est pas (honnêteté)

- Ce n'est **pas** une IA généraliste ni un substitut aux modèles de langage. Le
  `RuleBasedPerceiver` reste un parseur simple ; le grounding sérieux passe par
  un `LLMPerceiver`. Le noyau est une **couche de raisonnement et de garde-fou**.
- La sémantique de propagation est fondée et stable, mais ce n'est pas un
  prouveur logique complet (SAT/SMT) ni une inférence bayésienne exacte. C'est un
  choix assumé : un opérateur simple, prévisible et vérifiable, sur lequel des
  couches plus formelles pourront se greffer.
- « Solide » signifie ici : propriétés prouvées là où elles peuvent l'être,
  validées agressivement ailleurs (tests de propriété + adversariaux), zéro état
  caché, tout traçable. Pas « incassable » — cette notion n'existe pas.
