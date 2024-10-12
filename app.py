import streamlit as st
import pandas as pd
import re
from openai import OpenAI
import json
import logging
import profanity_check

# Configuración de logging
logging.basicConfig(level=logging.DEBUG)

# Configuración de la página
st.set_page_config(page_title="Chatbot de Restaurante", page_icon="🍽️")

# Inicialización del cliente OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Cargar datos y hacer que los nombres sean insensibles a mayúsculas/minúsculas
@st.cache_data
def load_data():
    try:
        menu_df = pd.read_csv('menu.csv')
        menu_df['Item'] = menu_df['Item'].str.lower().str.strip()
        menu_df['Category'] = menu_df['Category'].str.lower().str.strip()
        print("Productos disponibles:", menu_df['Item'].unique())
        
        cities_df = pd.read_csv('us-cities.csv')
        cities_df['City'] = cities_df['City'].str.lower().str.strip()
        delivery_cities = cities_df['City'].tolist()
        
        # Imprimir el contenido de delivery_cities para depurar
        print("Contenido de delivery_cities:", delivery_cities)
        print("Tipos de elementos en delivery_cities:", [type(city) for city in delivery_cities])
        
        return menu_df, delivery_cities
    except Exception as e:
        logging.error(f"Error al cargar los datos: {e}")
        return pd.DataFrame(), []

menu_df, delivery_cities = load_data()

if menu_df.empty:
    st.error("No se pudo cargar el menú. Por favor, verifica el archivo menu.csv.")
else:
    logging.info(f"Menú cargado correctamente. Categorías: {', '.join(menu_df['Category'].unique())}")
    logging.debug(f"Primeras filas del menú:\n{menu_df.head()}")

# Filtrar comentarios inapropiados
def is_profane(query):
    return profanity_check.predict([query])[0] == 1

# Funciones de manejo del menú
def get_menu():
    logging.debug("Función get_menu() llamada")
    if menu_df.empty:
        return "Lo siento, no pude cargar el menú. Por favor, contacta al soporte técnico."
    
    menu_text = "🍽️ **Nuestro Menú:**\n\n"
    for category, items in menu_df.groupby('Category'):
        menu_text += f"### {category.title()}\n"
        for _, item in items.iterrows():
            menu_text += f"- **{item['Item'].title()}** - {item['Serving Size']} - ${item['Price']:.2f}\n"
        menu_text += "\n"
    menu_text += "Para ver más detalles de una categoría específica, por favor pregúntame sobre ella."
    return menu_text

# Mejorar reconocimiento de variaciones comunes
def normalize_item_name(item_name):
    item_name = item_name.lower().strip()
    replacements = {
        "coca cola": "coca-cola",
        "pequeñas": "small",
        "grandes": "large",
        "medianas": "medium",
    }
    for old, new in replacements.items():
        item_name = item_name.replace(old, new)
    return item_name

# Validar que la categoría sea permitida
def get_category_details(category):
    logging.debug(f"Detalles solicitados para la categoría: {category}")
    category = category.lower().strip()
    category_items = menu_df[menu_df['Category'] == category]
    if category_items.empty:
        return f"Lo siento, no encontré información sobre la categoría '{category}'."
    
    details = f"Detalles de {category.title()}:\n\n"
    for _, item in category_items.iterrows():
        details += f"• {item['Item'].title()} - {item['Serving Size']} - ${item['Price']:.2f}\n"
    return details

# Funciones de manejo de entregas (coloca estas funciones después de las funciones del menú)
def check_delivery(city):
    city = city.strip().lower()
    if city in delivery_cities:
        return f"✅ Sí, realizamos entregas en {city.title()}."
    else:
        return f"❌ Lo siento, actualmente no realizamos entregas en {city.title()}."

def get_delivery_cities():
    # Asegurarse de que delivery_cities sea una lista de cadenas
    if all(isinstance(city, str) for city in delivery_cities):
        cities_list = '\n'.join([city.title() for city in delivery_cities])
        return f"Realizamos entregas en las siguientes ciudades:\n\n{cities_list}\n..."
    else:
        logging.error("La lista de ciudades de entrega contiene datos no válidos.")
        return "Lo siento, hubo un problema al cargar las ciudades de entrega."
    
# Funciones de manejo de pedidos
def calculate_total():
    total = 0
    for item, quantity in st.session_state.current_order.items():
        price = menu_df.loc[menu_df['Item'] == item.lower(), 'Price']
        if not price.empty:
            total += price.iloc[0] * quantity
        else:
            logging.warning(f"No se encontró el precio para {item}.")
    return total

# Filtrar peticiones incorrectas
def validate_quantity(quantity):
    if quantity <= 0 or quantity > 100:
        return "Lo siento, la cantidad debe estar entre 1 y 100."
    return None

# Funciones de manejo de pedidos

def add_to_order(item, quantity):
    logging.debug(f"Añadiendo al pedido: {quantity} x {item}")
    
    # Validar la cantidad
    quantity_validation = validate_quantity(quantity)
    if quantity_validation:
        return quantity_validation
    
    # Normalizar el nombre del producto ingresado por el usuario
    item_lower = normalize_item_name(item)
    menu_items_lower = [i.strip().lower() for i in menu_df['Item']]
    
    # Intentar una búsqueda exacta primero
    if item_lower in menu_items_lower:
        index = menu_items_lower.index(item_lower)
        actual_item = menu_df['Item'].iloc[index]
    else:
        # Si no se encuentra una coincidencia exacta, realizar una búsqueda parcial
        matching_items = menu_df[menu_df['Item'].str.contains(re.escape(item_lower), case=False)]
        if not matching_items.empty:
            actual_item = matching_items.iloc[0]['Item']
        else:
            return f"Lo siento, '{item}' no está en nuestro menú. Por favor, verifica el menú e intenta de nuevo."

    # Añadir el producto encontrado al pedido
    if actual_item in st.session_state.current_order:
        st.session_state.current_order[actual_item] += quantity
    else:
        st.session_state.current_order[actual_item] = quantity

    # Calcular el subtotal para el artículo recién agregado
    item_price = menu_df.loc[menu_df['Item'] == actual_item.lower(), 'Price'].iloc[0]
    item_total = item_price * quantity

    # Generar el desglose de los artículos
    response = f"Has añadido {quantity} {actual_item.title()}(s) a tu pedido. Subtotal para este artículo: ${item_total:.2f}.\n\n"
    
    # Mostrar el desglose del pedido completo
    response += "### Resumen de tu pedido actual:\n"
    order_total = 0
    for order_item, order_quantity in st.session_state.current_order.items():
        order_item_price = menu_df.loc[menu_df['Item'] == order_item.lower(), 'Price'].iloc[0]
        order_item_total = order_item_price * order_quantity
        order_total += order_item_total
        response += f"- {order_quantity} x {order_item.title()} - Subtotal: ${order_item_total:.2f}\n"
    
    response += f"\n**Total acumulado del pedido:** ${order_total:.2f}"
    
    return response

def remove_from_order(item):
    logging.debug(f"Eliminando del pedido: {item}")
    item_lower = normalize_item_name(item)
    for key in list(st.session_state.current_order.keys()):
        if key.lower() == item_lower:
            del st.session_state.current_order[key]
            total = calculate_total()
            return f"Se ha eliminado {key.title()} de tu pedido. El total actual es ${total:.2f}"
    return f"{item.title()} no estaba en tu pedido."

def modify_order(item, quantity):
    logging.debug(f"Modificando pedido: {quantity} x {item}")
    item_lower = normalize_item_name(item)
    for key in list(st.session_state.current_order.keys()):
        if key.lower() == item_lower:
            if quantity > 0:
                st.session_state.current_order[key] = quantity
                total = calculate_total()
                return f"Se ha actualizado la cantidad de {key.title()} a {quantity}. El total actual es ${total:.2f}"
            else:
                del st.session_state.current_order[key]
                total = calculate_total()
                return f"Se ha eliminado {key.title()} del pedido. El total actual es ${total:.2f}"
    return f"{item.title()} no está en tu pedido actual."

def start_order():
    return ("Para realizar un pedido, por favor sigue estos pasos:\n"
            "1. Revisa nuestro menú\n"
            "2. Dime qué items te gustaría ordenar\n"
            "3. Proporciona tu dirección de entrega\n"
            "4. Confirma tu pedido\n\n"
            "¿Qué te gustaría ordenar?")

def save_order_to_json(order):
    with open('orders.json', 'a') as f:
        json.dump(order, f)
        f.write('\n')

def confirm_order():
    if not st.session_state.current_order:
        return "No hay ningún pedido para confirmar. ¿Quieres empezar uno nuevo?"
    
    order_df = pd.DataFrame(list(st.session_state.current_order.items()), columns=['Item', 'Quantity'])
    order_df['Total'] = order_df.apply(lambda row: menu_df.loc[menu_df['Item'] == row['Item'].lower(), 'Price'].iloc[0] * row['Quantity'], axis=1)
    
    # Guardar en CSV
    order_df.to_csv('orders.csv', mode='a', header=False, index=False)
    
    # Guardar en JSON
    order_json = {
        'items': st.session_state.current_order,
        'total': calculate_total()
    }
    save_order_to_json(order_json)
    
    total = calculate_total()
    st.session_state.current_order = {}
    return f"¡Gracias por tu pedido! Ha sido confirmado y guardado en CSV y JSON. El total es ${total:.2f}"

def cancel_order():
    if not st.session_state.current_order:
        return "No hay ningún pedido para cancelar."
    st.session_state.current_order = {}
    return "Tu pedido ha sido cancelado."

def show_current_order():
    if not st.session_state.current_order:
        return "No tienes ningún pedido en curso."
    order_summary = "### Tu pedido actual:\n\n"
    total = 0
    for item, quantity in st.session_state.current_order.items():
        price = menu_df.loc[menu_df['Item'] == item.lower(), 'Price'].iloc[0]
        item_total = price * quantity
        total += item_total
        order_summary += f"- **{quantity} x {item.title()}** - ${item_total:.2f}\n"
    order_summary += f"\n**Total:** ${total:.2f}"
    return order_summary

# Función de manejo de consultas
def handle_query(query):
    logging.debug(f"Consulta recibida: {query}")

    # Clasificación de relevancia con GPT
    try:
        relevance_check = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "¿Está esta consulta relacionada con un restaurante o su menú? Responde con 'sí' o 'no'."},
                {"role": "user", "content": query}
            ],
            max_tokens=2,
            temperature=0.0,
        )
        relevance_response = relevance_check.choices[0].message.content.strip().lower()
        if relevance_response == 'no':
            return ("Lo siento, solo puedo ayudarte con temas relacionados al restaurante. "
                    "¿Te gustaría saber más sobre nuestro menú o realizar un pedido?")
    except Exception as e:
        logging.error(f"Error al verificar la relevancia con GPT: {e}")
        return ("Lo siento, no pude procesar tu consulta. Inténtalo nuevamente o pregunta algo "
                "relacionado con el restaurante.")

    query_lower = query.lower()
    order_match = re.findall(r'(\d+)\s+(.*?)\s*(?:y|,|\.|$)', query_lower)
    if order_match:
        response = ""
        for quantity, item in order_match:
            item = item.strip()
            response += add_to_order(item, int(quantity)) + "\n"
        return response.strip()
    
    if "menu" in query_lower or "carta" in query_lower or "menú" in query_lower:
        return get_menu()
    elif "ciudades" in query_lower and ("entrega" in query_lower or "reparte" in query_lower):
        return get_delivery_cities()
    elif re.search(r'\b(entrega|reparto)\b', query_lower):
        city_match = re.search(r'en\s+([\w\s]+)', query_lower)  # Captura nombres de ciudades de varias palabras
        if city_match:
            return check_delivery(city_match.group(1).strip())
        else:
            return get_delivery_cities()
    elif re.search(r'\b(precio|costo)\b', query_lower):
        item_match = re.search(r'(precio|costo)\s+de\s+(.+)', query_lower)
        if item_match:
            item = item_match.group(2)
            item = normalize_item_name(item)
            price = menu_df.loc[menu_df['Item'].str.contains(re.escape(item), case=False), 'Price']
            if not price.empty:
                return f"El precio de {item.title()} es ${price.iloc[0]:.2f}"
            else:
                return f"Lo siento, no encontré el precio de {item}."
    elif "mostrar pedido" in query_lower:
        return show_current_order()
    elif "cancelar pedido" in query_lower:
        return cancel_order()
    elif "confirmar pedido" in query_lower:
        return confirm_order()

    try:
        messages = st.session_state.messages + [{"role": "user", "content": query}]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": m["role"], "content": m["content"]}
                for m in messages
            ],
            max_tokens=150,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Error generating response with OpenAI: {e}")
        return ("Lo siento, no pude entender tu consulta. ¿Podrías reformularla con algo "
                "relacionado con nuestro restaurante?")


# Título de la aplicación
st.title("🍽️ Chatbot de Restaurante")

# Inicialización del historial de chat y pedido actual en la sesión de Streamlit
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "¡Hola! Bienvenido a nuestro restaurante. ¿En qué puedo ayudarte hoy? Si quieres ver nuestro menú, solo pídemelo."}
    ]
if "current_order" not in st.session_state:
    st.session_state.current_order = {}

# Mostrar mensajes existentes
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Campo de entrada para el usuario
if prompt := st.chat_input("¿En qué puedo ayudarte hoy?"):
    # Agregar mensaje del usuario al historial
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Mostrar el mensaje del usuario
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Generar respuesta del chatbot
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = handle_query(prompt)
        message_placeholder.markdown(full_response)
    
    # Agregar respuesta del chatbot al historial
    st.session_state.messages.append({"role": "assistant", "content": full_response})

# Mostrar el pedido actual
if st.session_state.current_order:
    st.sidebar.markdown("## Pedido Actual")
    st.sidebar.markdown(show_current_order())
    if st.sidebar.button("Confirmar Pedido"):
        st.sidebar.markdown(confirm_order())
    if st.sidebar.button("Cancelar Pedido"):
        st.sidebar.markdown(cancel_order())

logging.debug(f"Estado del pedido actual: {st.session_state.current_order}")
