"""
Backfill ponctuel pour la fonctionnalite "Lien Achats <-> Stock <-> Depenses".

Pour les achats/lignes_achat crees AVANT cette fonctionnalite :
  1. Tente de lier chaque ligne_achat sans stock_id a un article de stock
     existant par correspondance exacte (insensible a la casse/espaces) sur la designation.
  2. Pour chaque achat actif sans depense liee, cherche une depense "Achats
     Fournisseurs" orpheline (achat_id NULL) qui correspond par date + montant,
     et la lie. Sinon, cree une nouvelle depense liee.

Usage :
    python backfill_lien_achats.py            # mode apercu (dry-run), aucune ecriture
    python backfill_lien_achats.py --execute   # applique les changements
"""
import argparse
import psycopg2
import psycopg2.extras

from database import DB_CONFIG
import achats


def get_lignes_a_lier(cur):
    cur.execute("SELECT id, achat_id, designation FROM lignes_achat WHERE stock_id IS NULL")
    lignes = cur.fetchall()
    plan = []
    for ligne in lignes:
        cur.execute(
            'SELECT "idStock", "Designation" FROM stock WHERE LOWER(TRIM("Designation")) = LOWER(TRIM(%s))',
            (ligne["designation"],),
        )
        matches = cur.fetchall()
        plan.append((ligne, matches))
    return plan


def get_depenses_a_lier_ou_creer(cur, exclude_ids=()):
    cur.execute("""
        SELECT a.id, a.numero_facture, a.date_achat, a.montant_total, a.fournisseur_id
        FROM achats a
        WHERE a.statut_facture = 'Actif'
          AND NOT EXISTS (SELECT 1 FROM depense d WHERE d.achat_id = a.id)
        ORDER BY a.id
    """)
    achats_sans_depense = [a for a in cur.fetchall() if a["id"] not in exclude_ids]

    cur.execute("""
        SELECT id_depense, date_depense, montant
        FROM depense
        WHERE type_depense = 'Achats Fournisseurs' AND achat_id IS NULL
    """)
    orphelines = cur.fetchall()

    plan = []
    deja_utilisees = set()
    for a in achats_sans_depense:
        match = None
        for d in orphelines:
            if d["id_depense"] in deja_utilisees:
                continue
            if d["date_depense"] == a["date_achat"] and abs(d["montant"] - a["montant_total"]) < 0.01:
                match = d
                break
        if match:
            deja_utilisees.add(match["id_depense"])
            plan.append(("lier", a, match))
        else:
            plan.append(("creer", a, None))
    return plan


def afficher_plan(lignes_plan, depenses_plan, cur):
    print("=== Lignes d'achat a lier au stock ===")
    if not lignes_plan:
        print("  (aucune ligne_achat sans stock_id)")
    for ligne, matches in lignes_plan:
        if len(matches) == 1:
            print(f"  ligne_achat #{ligne['id']} (achat #{ligne['achat_id']}, '{ligne['designation']}') -> stock #{matches[0]['idStock']} ('{matches[0]['Designation']}')")
        elif len(matches) == 0:
            print(f"  ligne_achat #{ligne['id']} (achat #{ligne['achat_id']}, '{ligne['designation']}') -> AUCUNE correspondance, laissee non liee")
        else:
            ids = ", ".join(f"#{m['idStock']} ('{m['Designation']}')" for m in matches)
            print(f"  ligne_achat #{ligne['id']} (achat #{ligne['achat_id']}, '{ligne['designation']}') -> AMBIGU ({len(matches)} correspondances : {ids}), laissee non liee")

    print("\n=== Depenses a lier ou creer pour les achats actifs ===")
    if not depenses_plan:
        print("  (tous les achats actifs ont deja une depense liee)")
    for action, a, match in depenses_plan:
        fournisseur_nom = achats._get_fournisseur_nom(cur, a["fournisseur_id"])
        if action == "lier":
            print(f"  achat #{a['id']} (facture '{a['numero_facture']}', {a['date_achat']}, {a['montant_total']} FCFA) -> LIER a la depense existante #{match['id_depense']}")
        else:
            description = achats._description_depense_achat(fournisseur_nom, a["numero_facture"])
            print(f"  achat #{a['id']} (facture '{a['numero_facture']}', {a['date_achat']}, {a['montant_total']} FCFA) -> CREER une depense : date={a['date_achat']}, montant={a['montant_total']}, description='{description}'")


def appliquer_plan(lignes_plan, depenses_plan, cur):
    for ligne, matches in lignes_plan:
        if len(matches) == 1:
            cur.execute("UPDATE lignes_achat SET stock_id = %s WHERE id = %s", (matches[0]["idStock"], ligne["id"]))

    for action, a, match in depenses_plan:
        if action == "lier":
            cur.execute("UPDATE depense SET achat_id = %s WHERE id_depense = %s", (a["id"], match["id_depense"]))
        else:
            fournisseur_nom = achats._get_fournisseur_nom(cur, a["fournisseur_id"])
            description = achats._description_depense_achat(fournisseur_nom, a["numero_facture"])
            cur.execute("""
                INSERT INTO depense (date_depense, type_depense, montant, description, achat_id)
                VALUES (%s, 'Achats Fournisseurs', %s, %s, %s)
            """, (a["date_achat"], a["montant_total"], description, a["id"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Applique les changements (sinon, mode apercu)")
    parser.add_argument("--exclude", default="", help="Liste d'IDs d'achats a exclure du backfill des depenses, separes par des virgules")
    args = parser.parse_args()
    exclude_ids = {int(x) for x in args.exclude.split(",") if x.strip()}

    conn = psycopg2.connect(**DB_CONFIG)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    cur = conn.cursor()

    lignes_plan = get_lignes_a_lier(cur)
    depenses_plan = get_depenses_a_lier_ou_creer(cur, exclude_ids)

    afficher_plan(lignes_plan, depenses_plan, cur)

    if args.execute:
        appliquer_plan(lignes_plan, depenses_plan, cur)
        conn.commit()
        print("\n=== Changements appliques et commites ===")
    else:
        conn.rollback()
        print("\n=== Mode apercu : aucun changement applique (relancer avec --execute pour appliquer) ===")

    conn.close()


if __name__ == "__main__":
    main()
