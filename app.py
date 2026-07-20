import streamlit as st

# 1. Configuration de la page (Doit TOUJOURS être la première commande)
st.set_page_config(
    page_title="Yassir Performance",
    page_icon="🍔",
    layout="wide", # Utilise toute la largeur de l'écran (très important pour les tableaux)
    initial_sidebar_state="expanded"
)

# 2. MENU LATÉRAL (Sidebar) : La zone de contrôle
with st.sidebar:
    st.markdown("## ⚙️ Filtres et Contrôles")
    
    # Des menus déroulants modernes
    semaine_choisie = st.selectbox("📅 Sélectionner la semaine", ["Week 27", "Week 26", "Week 25"])
    zone_choisie = st.multiselect("📍 Filtrer par Zone", ["Agdal", "Hay Riad", "Oasis", "Centre"], default=["Agdal", "Hay Riad"])
    
    st.markdown("---")
    st.markdown("💡 *Le tableau de bord se met à jour instantanément à chaque clic.*")

# 3. EN-TÊTE PRINCIPAL
st.title(f"📊 Dashboard Performances - {semaine_choisie}")
st.markdown("Analyse des restaurants, taux d'automation et surveillance des Tops/Flops.")

# 4. LES KPIs (Cartes de métriques) : L'impact visuel immédiat
st.markdown("### 🏆 Vue d'ensemble")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="Commandes Livrées", value="1 245", delta="-5% WoW")
with col2:
    st.metric(label="Taux d'Acceptation", value="82%", delta="3% WoW")
with col3:
    st.metric(label="GMV Total", value="125K MAD", delta="-2% WoW")
with col4:
    # delta_color="inverse" veut dire qu'une baisse des annulations sera verte !
    st.metric(label="Annulations", value="45", delta="-10% WoW", delta_color="inverse")

st.markdown("---")

# 5. NAVIGATION PAR ONGLETS (Pour ne pas surcharger l'écran)
tab1, tab2, tab3 = st.tabs(["📈 Overview Pipeline", "🚨 Tops & Flops", "❌ Annulations"])

with tab1:
    st.markdown("#### 📋 Performances détaillées de la Pipeline")
    st.info("Ici, nous mettrons le grand tableau global avec la coloration conditionnelle pour voir d'un coup d'œil qui performe.")
    # Le vrai st.dataframe(df) viendra ici

with tab2:
    st.markdown("#### 📉 Les plus grosses baisses de la semaine")
    st.warning("Ici, on mettra un graphique à barres horizontales pour visualiser les baisses, suivi de ton tableau du Top 50 des pires chutes.")

with tab3:
    st.markdown("#### 🔍 Analyse des raisons d'annulation (Restaurant Rejected)")
    st.error("Ici, nous afficherons un magnifique graphique en camembert (Pie chart) pour voir la répartition : Indisponible, Fermé, etc.")
