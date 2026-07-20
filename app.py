import streamlit as st
import pandas as pd

# ==========================================
# 1. CONFIGURATION DE LA PAGE
# (Cette ligne doit obligatoirement être la première commande Streamlit)
# ==========================================
st.set_page_config(page_title="Yassir Performance", page_icon="🍔", layout="wide")

# ==========================================
# 2. EN-TÊTE ET CONTRÔLES (HEADER)
# ==========================================
st.title("📊 Dashboard Performances Yassir")
st.markdown("---")

st.markdown("### ⚙️ Configuration & Données")
col_am, col_upload, col_week = st.columns(3)

with col_am:
    am_choisi = st.selectbox("Pipeline", ["Houda", "Yassine", "Sara", "Amine"], label_visibility="collapsed")
    st.caption(f"📂 Fichier Config lu : `Pipeline - {am_choisi}.csv`")

with col_upload:
    fichier_data = st.file_uploader("Upload Data (admin-earnings...csv)", type=["csv", "xlsx"], label_visibility="collapsed")

with col_week:
    semaine_choisie = st.selectbox("Semaine d'analyse", ["Week courante", "Week précédente"], label_visibility="collapsed")

st.markdown("---")

# Barrière de sécurité : On arrête le code ici tant qu'il n'y a pas de fichier
if fichier_data is None:
    st.info("👋 Bienvenue ! Veuillez uploader le fichier Data de la semaine pour générer le tableau de bord.")
    st.stop()

# ==========================================
# 3. MOTEUR DE DONNÉES (TRAITEMENT PANDAS)
# ==========================================
try:
    # Lecture des fichiers
    df_pipeline = pd.read_csv(f"Pipeline - {am_choisi}.csv")
    df_data = pd.read_csv(fichier_data)

    # Fusion des données (VLOOKUP via Restaurant ID)
    df_merged = pd.merge(df_data, df_pipeline, on="Restaurant ID", how="inner")

    # Préparation du tableau de l'onglet 2 (Overview)
    overview_table = df_merged.groupby(['Segment', 'Restaurant Name']).agg(
        Requested=('order id', 'count'),
        Delivered=('status', lambda x: (x == 'Delivered').sum()),
        GMV=('item total', lambda x: x[df_merged.loc[x.index, 'status'] == 'Delivered'].sum()),
        CA=('admin earnings', lambda x: x[df_merged.loc[x.index, 'status'] == 'Delivered'].sum()) # Remplacez si le CA se calcule autrement
    ).reset_index()

    # Calcul des KPIs (Taux et AOV)
    overview_table['Success Rate'] = (overview_table['Delivered'] / overview_table['Requested']).fillna(0)
    overview_table['AOV'] = (overview_table['GMV'] / overview_table['Delivered']).fillna(0)

    # Création d'une copie formatée pour l'affichage (textes)
    df_display = overview_table.copy()
    df_display['Success Rate'] = df_display['Success Rate'].apply(lambda x: f"{x:.1%}")
    df_display['GMV'] = df_display['GMV'].apply(lambda x: f"{x:,.2f} MAD")
    df_display['CA'] = df_display['CA'].apply(lambda x: f"{x:,.2f} MAD")
    df_display['AOV'] = df_display['AOV'].apply(lambda x: f"{x:,.2f} MAD")

except Exception as e:
    st.error(f"Une erreur est survenue lors du traitement des données. Vérifiez le format de vos fichiers : {e}")
    st.stop()

# ==========================================
# 4. STRUCTURE DES ONGLETS (TABS)
# ==========================================
tab_global, tab_pipeline, tab_flops, tab_annulations = st.tabs([
    "🌍 Analyse Global", 
    "📈 Overview Pipeline", 
    "🚨 Tops & Flops", 
    "❌ Annulations"
])

# ----------------------------------------
# ONGLET 1 : ANALYSE GLOBAL
# ----------------------------------------
with tab_global:
    st.markdown("#### 🌍 Analyse Macro des Performances")
    
    vue_temporelle = st.radio(
        "Sélectionnez la vue temporelle :",
        ["📅 Jour", "📊 Week over Week (WoW)", "📆 Month over Month (MoM)"],
        horizontal=True,
        label_visibility="collapsed"
    )
    st.markdown("---")
    
    # Structure du tableau de base (Variances en placeholders en attendant l'intégration des semaines précédentes)
    data_macro = {
        "Période": ["Week 27", "Week 26", "Week 25"],
        "Reçu": [1500, 1420, 1300],
        "Livré": [1245, 1200, 1150],
        "GMV (MAD)": [125000, 118000, 110000],
        "CA (MAD)": [18750, 17700, 16500],
        "AOV (MAD)": [100.4, 98.3, 95.6],
        "V. Reçu": ["+5.6%", "+9.2%", "-"],
        "V. Livré": ["+3.7%", "+4.3%", "-"],
        "V. GMV": ["+5.9%", "+7.2%", "-"],
        "V. CA": ["+5.9%", "+7.2%", "-"],
        "V. AOV": ["+2.1%", "+2.8%", "-"]
    }
    df_global = pd.DataFrame(data_macro)
    
    st.dataframe(df_global, use_container_width=True, hide_index=True)

# ----------------------------------------
# ONGLET 2 : OVERVIEW PIPELINE
# ----------------------------------------
with tab_pipeline:
    st.markdown(f"#### 📋 Tableau de Synthèse : Pipeline {am_choisi}")
    # On affiche le tableau formaté (df_display) et non les chiffres bruts
    st.dataframe(df_display, use_container_width=True, hide_index=True)

# ----------------------------------------
# ONGLET 3 : TOPS & FLOPS
# ----------------------------------------
with tab_flops:
    st.markdown("#### 📉 Classement Hebdomadaire")
    
    col_top, col_flop = st.columns(2)
    
    with col_top:
        st.success("**🏆 Top 10 Livraisons**")
        top_10 = overview_table.sort_values(by="Delivered", ascending=False).head(10)
        st.dataframe(top_10[['Restaurant Name', 'Delivered', 'Success Rate']], hide_index=True, use_container_width=True)
        
    with col_flop:
        st.error("**⚠️ Flop 10 Livraisons**")
        flop_10 = overview_table.sort_values(by="Delivered", ascending=True).head(10)
        st.dataframe(flop_10[['Restaurant Name', 'Delivered', 'Success Rate']], hide_index=True, use_container_width=True)

# ----------------------------------------
# ONGLET 4 : ANNULATIONS
# ----------------------------------------
with tab_annulations:
    st.markdown("#### ❌ Analyse des Annulations")
    
    # On filtre toutes les commandes dont le statut contient "Cancelled"
    df_cancelled = df_merged[df_merged['status'].str.contains('Cancelled', case=False, na=False)]
    
    if not df_cancelled.empty:
        # On compte les raisons d'annulation (colonne 'cancellation reason ')
        cancel_reasons = df_cancelled['cancellation reason '].value_counts().reset_index()
        cancel_reasons.columns = ['Raison d\'annulation', 'Nombre de commandes']
        
        col_chart, col_table = st.columns([2, 1])
        
        with col_chart:
            # Création d'un graphique en barres simple et natif
            st.bar_chart(cancel_reasons.set_index('Raison d\'annulation'))
            
        with col_table:
            st.dataframe(cancel_reasons, hide_index=True, use_container_width=True)
    else:
        st.success("🎉 Excellente nouvelle : Aucune annulation trouvée dans les données de cette semaine !")
