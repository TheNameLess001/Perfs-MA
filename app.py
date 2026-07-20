import streamlit as st

# 1. Configuration de la page (Toujours en premier)
st.set_page_config(
    page_title="Yassir Performance",
    page_icon="🍔",
    layout="wide" # Exploite 100% de la largeur de l'écran
)

# 2. EN-TÊTE ET TITRE
st.title("📊 Dashboard Performances Yassir")
st.markdown("Analyse des performances hebdomadaires par Account Manager.")
st.markdown("---")

# 3. PANNEAU DE CONTRÔLE EN HAUT (Filtres et Upload)
st.markdown("### ⚙️ Configuration & Données")

# On divise le haut de l'écran en 3 colonnes de largeur égale
col_am, col_upload, col_week = st.columns(3)

with col_am:
    st.markdown("**1. Choisir l'Account Manager**")
    # L'utilisateur choisit l'AM. Plus tard, le code ira lire "Pipeline-Houda.csv" ou "Pipeline-Yassine.csv"
    am_choisi = st.selectbox("Sélection de la Pipeline", ["Houda", "Yassine", "Sara", "Amine"], label_visibility="collapsed")
    st.caption(f"📂 Fichier source : `Pipeline-{am_choisi}`")

with col_upload:
    st.markdown("**2. Charger les performances**")
    # Le composant magique pour uploader la donnée à la volée
    fichier_data = st.file_uploader("Upload Data", type=["xlsx", "csv"], label_visibility="collapsed")

with col_week:
    st.markdown("**3. Filtre d'affichage**")
    semaine_choisie = st.selectbox("Semaine d'analyse", ["Week 27", "Week 26", "Week 25"], label_visibility="collapsed")
    zone_choisie = st.multiselect("Filtrer par Segment", ["Segment A", "Segment B", "Segment C"], placeholder="Tous les segments")

st.markdown("---")

# 4. SÉCURITÉ UX : On attend le fichier
if fichier_data is None:
    # Si aucun fichier n'est uploadé, on affiche un message d'attente stylé et on arrête l'affichage ici
    st.info("👋 Bienvenue ! Veuillez uploader le fichier de Data dans le panneau ci-dessus pour générer votre tableau de bord.")
    st.stop()

# ==========================================
# 🛑 TOUT CE QUI SUIT NE S'AFFICHE QUE SI LE FICHIER EST UPLOADÉ
# ==========================================

# 5. LES KPIs (Vue d'ensemble)
st.markdown(f"### 🏆 Vue d'ensemble - {am_choisi} ({semaine_choisie})")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.metric(label="Commandes Livrées", value="1 245", delta="-5% WoW")
with kpi2:
    st.metric(label="Taux d'Acceptation", value="82%", delta="3% WoW")
with kpi3:
    st.metric(label="GMV Total", value="125K MAD", delta="-2% WoW")
with kpi4:
    st.metric(label="Annulations", value="45", delta="-10% WoW", delta_color="inverse")

st.markdown("---")

# 6. NAVIGATION PAR ONGLETS
tab1, tab2, tab3 = st.tabs(["📈 Overview Pipeline", "🚨 Tops & Flops", "❌ Annulations"])

with tab1:
    st.markdown(f"#### 📋 Performances détaillées de la Pipeline de {am_choisi}")
    st.success("Le tableau complet apparaîtra ici, fusionné entre le fichier uploadé et la Config de l'AM.")

with tab2:
    st.markdown("#### 📉 Classement des baisses (Drops)")
    st.warning("Graphique des 50 pires baisses de commandes.")

with tab3:
    st.markdown("#### 🔍 Raisons d'annulation (Restaurant Rejected)")
    st.error("Graphique de répartition (Pie Chart) des annulations.")
