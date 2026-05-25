import streamlit as st
st.markdown("""
<style>
.vertical-slider {
    transform: rotate(-90deg);
    width: 200px;
    margin-top: 100px;
    margin-left: -50px;
}
</style>
<div class='vertical-slider'>
""", unsafe_allow_html=True)
st.slider("Test", 0, 100, 50)
st.markdown("</div>", unsafe_allow_html=True)
