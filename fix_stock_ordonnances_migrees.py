"""
Correction ponctuelle pour les ordonnances migrees depuis l'ancienne base SQLite
(cf. migrate.py sur le serveur) marquees stock_applique=true par la migration
Phase 7 (2026_06_15_ordonnance_stock_applique.sql), alors qu'aucune logique de
decrementation n'existait encore dans ce code a l'epoque de leur creation.

Concerne uniquement les ordonnances migrees ayant au moins une ligne liee a un
article de stock reel (stock_id NOT NULL) : id 5, 35, 36, 38 (identifiees par
investigation manuelle, cf. conversation).

Pour chacune : repasse stock_applique a false puis re-applique la decrementation
via le meme circuit que ordonnances.update_ordonnance (_appliquer_mouvement_stock),
avant de remettre stock_applique a true.

Usage :
    python fix_stock_ordonnances_migrees.py            # mode apercu (dry-run), aucune ecriture
    python fix_stock_ordonnances_migrees.py --execute   # applique les changements
"""
import argparse
import psycopg2
import psycopg2.extras

from database import DB_CONFIG

ORDONNANCE_IDS = (5, 35, 36, 38)


def get_plan(cur):
    cur.execute("""
        SELECT o.id, o.stock_applique, o.est_validee, p.nom, p.prenom
        FROM ordonnance o
        LEFT JOIN patients p ON o.patient_id = p.id
        WHERE o.id = ANY(%s)
        ORDER BY o.id
    """, (list(ORDONNANCE_IDS),))
    ordonnances = cur.fetchall()

    plan = []
    for o in ordonnances:
        cur.execute("""
            SELECT lo.id, lo.designation, lo.quantite, lo.stock_id, s."Designation" AS stock_designation, s."Quantite" AS stock_qte_actuelle
            FROM ligne_ordonnance lo
            LEFT JOIN stock s ON s."idStock" = lo.stock_id
            WHERE lo.ordonnance_id = %s AND lo.stock_id IS NOT NULL
            ORDER BY lo.id
        """, (o["id"],))
        lignes = cur.fetchall()
        plan.append((o, lignes))
    return plan


def afficher_plan(plan):
    print("=== Ordonnances a decrementer (mode apercu) ===")
    for o, lignes in plan:
        nom = f"{o['nom']} {o['prenom']}" if o["nom"] else "-"
        print(f"\nOrdonnance #{o['id']} ({nom}) - stock_applique actuel = {o['stock_applique']}, est_validee = {o['est_validee']}")
        if not lignes:
            print("  (aucune ligne avec stock_id, rien a faire)")
            continue
        for l in lignes:
            nouvelle_qte = l["stock_qte_actuelle"] - l["quantite"]
            print(f"  - {l['designation']} (stock #{l['stock_id']} '{l['stock_designation']}') : quantite ordonnance = {l['quantite']}, "
                  f"stock actuel = {l['stock_qte_actuelle']} -> {nouvelle_qte} apres decrementation")


def appliquer_plan(cur, plan):
    for o, lignes in plan:
        cur.execute("UPDATE ordonnance SET stock_applique = false WHERE id = %s", (o["id"],))
        for l in lignes:
            cur.execute(
                'UPDATE stock SET "Quantite" = "Quantite" - %s WHERE "idStock" = %s',
                (l["quantite"], l["stock_id"])
            )
        cur.execute("UPDATE ordonnance SET stock_applique = true WHERE id = %s", (o["id"],))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Applique les changements (sinon, mode apercu)")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    cur = conn.cursor()

    plan = get_plan(cur)
    afficher_plan(plan)

    if args.execute:
        appliquer_plan(cur, plan)
        conn.commit()
        print("\n=== Changements appliques et commites ===")
    else:
        conn.rollback()
        print("\n=== Mode apercu : aucun changement applique (relancer avec --execute pour appliquer) ===")

    conn.close()


if __name__ == "__main__":
    main()
