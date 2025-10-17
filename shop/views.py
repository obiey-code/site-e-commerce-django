from django.shortcuts import redirect, render
from .models import Product, Commande
from django.core.paginator import Paginator


from django.shortcuts import  get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Cart, CartItem, Order, OrderItem
from .forms import AddToCartForm, OrderCreateForm
from django.db import transaction

# Create your views here.
def index(request):
    product_object = Product.objects.all()
    item_name = request.GET.get('item-name')
    if item_name !='' and item_name is not None:
        product_object = Product.objects.filter(title__icontains=item_name)
    paginator = Paginator(product_object, 4)
    page = request.GET.get('page')
    product_object = paginator.get_page(page)
    return render(request, 'shop/index.html', {'product_object': product_object})

def detail(request, myid):
    product_object = Product.objects.get(id=myid)
    return render(request, 'shop/detail.html', {'product': product_object}) 

def checkout(request):
    if request.method == "POST":
        items = request.POST.get('items')
        total = request.POST.get('total')
        nom = request.POST.get('nom')
        email = request.POST.get('email')
        address = request.POST.get('address')
        ville = request.POST.get('ville')
        pays = request.POST.get('pays')
        zipcode= request.POST.get('zipcode')
        com = Commande(items=items,total=total, nom=nom, email=email, address=address, ville=ville, pays=pays, zipcode=zipcode)
        com.save()
        return redirect('confirmation')


    return render(request, 'shop/checkout.html') 

def confimation(request):
    info = Commande.objects.all()[:1]
    for item in info:
        nom = item.nom
    return render(request, 'shop/confirmation.html', {'name': nom})       














    

# --- Fonctions utilitaires pour le panier ---

def get_or_create_cart(request):
    cart = None
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(user=request.user)
    else:
        session_key = request.session.session_key
        if not session_key:
            request.session.save()
            session_key = request.session.session_key
        
        # Merge anonymous cart with user cart if user logs in after adding items
        if request.user.is_authenticated and session_key:
            try:
                anon_cart = Cart.objects.get(session_key=session_key)
                user_cart, created = Cart.objects.get_or_create(user=request.user)
                # Merge items from anonymous cart to user's cart
                for anon_item in anon_cart.items.all():
                    existing_item = user_cart.items.filter(product=anon_item.product).first()
                    if existing_item:
                        existing_item.quantity += anon_item.quantity
                        existing_item.save()
                    else:
                        CartItem.objects.create(
                            cart=user_cart,
                            product=anon_item.product,
                            quantity=anon_item.quantity,
                            price_at_addition=anon_item.price_at_addition
                        )
                anon_cart.delete() # Delete the anonymous cart
                cart = user_cart
                request.session['cart_id'] = cart.id # Update session with user cart id
            except Cart.DoesNotExist:
                pass # No anonymous cart to merge
        
        if not cart: # If still no cart (e.g., first time anonymous user)
            cart, created = Cart.objects.get_or_create(session_key=session_key)
    
    request.session['cart_id'] = cart.id # shop cart ID in session for convenience
    return cart

# --- Vues du panier ---

def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart = get_or_create_cart(request)

    form = AddToCartForm(request.POST or None)
    if form.is_valid():
        quantity = form.cleaned_data['quantity']
        
        if product.stock < quantity:
            messages.error(request, f"Seulement {product.stock} exemplaires de {product.name} sont disponibles en stock.")
            return redirect('product_detail', product_id=product.id)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity, 'price_at_addition': product.price}
        )
        if not created:
            # Vérifier le stock avant d'ajouter
            if product.stock < (cart_item.quantity + quantity):
                messages.error(request, f"Ajout de {quantity} de {product.name} dépasserait le stock disponible ({product.stock}). Vous avez déjà {cart_item.quantity} dans votre panier.")
                return redirect('product_detail', product_id=product.id)
            cart_item.quantity += quantity
            cart_item.save()
            messages.success(request, f"{quantity} exemplaires de {product.name} ajoutés au panier.")
        else:
            messages.success(request, f"{product.name} ajouté au panier.")

    return redirect('cart_detail') # Rediriger vers la page du panier

def cart_detail(request):
    cart = get_or_create_cart(request)
    return render(request, 'shop/cart_detail.html', {'cart': cart})

def update_cart_item(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id)
    cart = get_or_create_cart(request)

    # Vérifiez que l'article appartient bien au panier de l'utilisateur/session actuel
    if cart_item.cart != cart:
        messages.error(request, "Cet article n'appartient pas à votre panier.")
        return redirect('cart_detail')

    if request.method == 'POST':
        form = AddToCartForm(request.POST) # Utilise le même formulaire pour la quantité
        if form.is_valid():
            new_quantity = form.cleaned_data['quantity']

            if new_quantity <= 0:
                cart_item.delete()
                messages.success(request, "Article supprimé du panier.")
            else:
                if cart_item.product.stock < new_quantity:
                    messages.error(request, f"Seulement {cart_item.product.stock} exemplaires de {cart_item.product.name} sont disponibles en stock.")
                    return redirect('cart_detail')
                cart_item.quantity = new_quantity
                cart_item.save()
                messages.success(request, "Quantité mise à jour.")
    return redirect('cart_detail')

def remove_from_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id)
    cart = get_or_create_cart(request)

    # Vérifiez que l'article appartient bien au panier de l'utilisateur/session actuel
    if cart_item.cart != cart:
        messages.error(request, "Cet article n'appartient pas à votre panier.")
        return redirect('cart_detail')

    if request.method == 'POST':
        cart_item.delete()
        messages.success(request, "Article supprimé du panier.")
    return redirect('cart_detail')

def clear_cart(request):
    cart = get_or_create_cart(request)
    if request.method == 'POST':
        if cart.items.exists():
            cart.items.all().delete()
            messages.success(request, "Votre panier a été vidé avec succès.")
        else:
            messages.info(request, "Votre panier est déjà vide.")
    return redirect('cart_detail')

# --- Vues de la commande ---

@login_required # Seuls les utilisateurs connectés peuvent passer commande
@transaction.atomic # Pour s'assurer que toutes les opérations de commande réussissent ou échouent ensemble
def create_order(request):
    cart = get_or_create_cart(request)

    if not cart.items.exists():
        messages.warning(request, "Votre panier est vide. Veuillez ajouter des articles avant de passer commande.")
        return redirect('cart_detail')

    # Vérifier le stock final avant de créer la commande
    for item in cart.items.all():
        if item.product.stock < item.quantity:
            messages.error(request, f"Erreur de stock pour {item.product.name}. Seulement {item.product.stock} disponibles. Veuillez ajuster votre panier.")
            return redirect('cart_detail')


    if request.method == 'POST':
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.user = request.user
            order.total_amount = cart.get_total() # Calculer le total du panier
            order.save()

            for item in cart.items.all():
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    price=item.price_at_addition, # Utiliser le prix enregistré dans CartItem
                    quantity=item.quantity
                )
                # Décrémenter le stock du produit
                item.product.stock -= item.quantity
                item.product.save()

            cart.items.all().delete() # Vider le panier après la commande
            messages.success(request, f"Votre commande #{order.id} a été créée avec succès!")
            return redirect('order_detail', order_id=order.id)
    else:
        # Pré-remplir le formulaire avec les infos de l'utilisateur si disponibles
        initial_data = {}
        if request.user.is_authenticated:
            initial_data = {
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email,
                # Ajoutez d'autres champs si l'utilisateur a un profil avec des adresses
            }
        form = OrderCreateForm(initial=initial_data)

    return render(request, 'shop/order_create.html', {'cart': cart, 'form': form})

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'shop/order_detail.html', {'order': order})

@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'shop/order_history.html', {'orders': orders})

# Vue simple pour les produits
def product_list(request):
    products = Product.objects.filter(is_active=True)
    return render(request, 'shop/product_list.html', {'products': products})

def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    form = AddToCartForm()
    return render(request, 'shop/product_detail.html', {'product': product, 'form': form})   