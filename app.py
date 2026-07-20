import streamlit as st
import pandas as pd

st.set_page_config(page_title="Yassir Performance", page_icon="🍔", layout="wide")

st.title("📊 Dashboard Performances Yassir")
st.markdown("---")

st.markdown("### ⚙️ Configuration & Données")
col_am, col_upload, col_week = st.columns(3)

with col_am:
    am_choisi = st.selectbox("Pipeline", ["Houda", "Yassine", "Sara", "Amine"], label_visibility="collapsed")
    st.caption(f"📂 Fichier Config : `Pipeline - {am_choisi}.csv`")

with col_upload:
    fichier_data = st.file_uploader("Upload Data (admin-earnings...csv)", type=["csv", "xlsx"], label_visibility="collapsed")

with col_week:
    semaine_choisie = st.selectbox("Semaine d'analyse", ["Week courante", "Week précédente"], label_visibility="collapsed")

st.markdown("---")

if fichier_data is None:
    st.info("👋 Veuillez uploader le fichier Data de la semaine pour générer le tableau de bord.")
    st.stop()

# ==========================================
# ⚙️ MOTEUR DE TRAITEMENT DES DONNÉES (PANDAS)
# ==========================================

try:
    # 1. Lecture du fichier Config de l'AM
    # (En production, le fichier doit être dans le même dossier que app.py)
    nom_fichier_pipeline = f"Pipeline - {am_choisi}.csv"
    df_pipeline = pd.read_csv(nom_fichier_pipeline)
    
    # 2. Lecture du gros fichier Data uploadé
    df_data = pd.read_csv(fichier_data)

    # 3. LA FUSION MAGIQUE (L'équivalent du VLOOKUP)
    # On garde toutes les commandes du fichier data qui correspondent aux Restos de l'AM
    df_merged = pd.merge(df_data, df_pipeline, on="Restaurant ID", how="inner")

    # 4. CRÉATION DU TABLEAU DE SYNTHÈSE (Overview)
    # On calcule les indicateurs pour chaque restaurant
    overview_table = df_merged.groupby(['Segment', 'Restaurant Name']).agg(
        Requested=('order id', 'count'), # Nombre total de commandes reçues
        Delivered=('status', lambda x: (x == 'Delivered').sum()), # Commandes livrées
        GMV=('item total', lambda x: x[df_merged.loc[x.index, 'status'] == 'Delivered'].sum()) # Chiffre d'affaires livré
    ).reset_index()

    # 5. Calculs mathématiques (Taux)
    overview_table['Success Rate'] = (overview_table['Delivered'] / overview_table['Requested']).fillna(0)
    
    # Formatage propre (pourcentage et monnaie)
    overview_table['Success Rate'] = overview_table['Success Rate'].apply(lambda x: f"{x:.1%}")
    overview_table['GMV'] = overview_table['GMV'].apply(lambda x: f"{x:,.2f} MAD")

except Exception as e:
    st.error(f"Une erreur est survenue lors du traitement des données : {e}")
    st.stop()

# ==========================================
# 📈 AFFICHAGE DU DASHBOARD
# ==========================================

# Affichage des KPIs globaux
total_req = overview_table['Requested'].sum()
total_del = overview_table['Delivered'].sum()
total_gmv = df_merged[df_merged['status'] == 'Delivered']['item total'].sum()

kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric(label="Total Requested", value=total_req)
kpi2.metric(label="Total Delivered", value=total_del)
kpi3.metric(label="GMV Total (Livré)", value=f"{total_gmv:,.0f} MAD")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📈 Overview Pipeline", "🚨 Tops & Flops", "❌ Annulations"])

with tab1:
    st.markdown(f"#### 📋 Tableau de Synthèse : {am_choisi}")
    # On affiche le tableau généré de manière interactive
    st.dataframe(
        overview_table, 
        use_container_width=True, # Prend toute la largeur
        hide_index=True # Cache la numérotation moche de gauche
    )

with tab2:
    st.markdown("#### 📉 Section en cours de construction...")

with tab3:
    st.markdown("#### 🔍 Section en cours de construction...")
