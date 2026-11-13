package com.example.stockroom

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.gson.Gson
import kotlinx.coroutines.launch
import retrofit2.HttpException

class AppViewModel(app: Application) : AndroidViewModel(app) {
    // Token is kept in app-private storage. For stricter protection use EncryptedSharedPreferences.
    private val prefs = app.getSharedPreferences("session", Context.MODE_PRIVATE)
    private val gson = Gson()

    var token by mutableStateOf(prefs.getString("token", null)); private set
    var user by mutableStateOf(
        prefs.getString("user", null)?.let { runCatching { gson.fromJson(it, User::class.java) }.getOrNull() }
    ); private set
    private val api = ApiClient.create { token }

    var loading by mutableStateOf(false); private set
    var message by mutableStateOf<String?>(null)
    var dashboard by mutableStateOf<Dashboard?>(null); private set
    var products by mutableStateOf<List<Product>>(emptyList()); private set
    var orders by mutableStateOf<List<OrderRow>>(emptyList()); private set
    var customers by mutableStateOf<List<Customer>>(emptyList()); private set
    var orderProducts by mutableStateOf<List<Product>>(emptyList()); private set

    val canManage get() = user?.role == "manager" || user?.role == "admin"

    private fun run(block: suspend () -> Unit) = viewModelScope.launch {
        loading = true
        try {
            block()
        } catch (e: Throwable) {
            if (e is HttpException && e.code() == 401 && token != null) clearSession() else message = e.friendly()
        } finally {
            loading = false
        }
    }

    private fun clearSession() {
        prefs.edit().clear().apply()
        token = null; user = null; dashboard = null; products = emptyList(); orders = emptyList()
    }

    fun login(email: String, password: String) = run {
        val res = api.login(LoginReq(email.trim(), password))
        prefs.edit().putString("token", res.token).putString("user", gson.toJson(res.user)).apply()
        token = res.token; user = res.user
    }

    fun logout() {
        viewModelScope.launch { runCatching { api.logout() } }
        clearSession()
    }

    fun loadDashboard() = run { dashboard = api.dashboard() }

    fun loadProducts(query: String = "", lowOnly: Boolean = false) = run {
        products = api.products(query.ifBlank { null }, if (lowOnly) true else null).items
    }

    fun moveStock(product: Product, quantity: Int, reason: String, stockIn: Boolean, query: String, lowOnly: Boolean) = run {
        val body = MoveReq(product.id, quantity, reason.ifBlank { null })
        if (stockIn) api.stockIn(body) else api.stockOut(body)
        message = "Stock updated for ${product.name}"
        products = api.products(query.ifBlank { null }, if (lowOnly) true else null).items
    }

    fun loadOrders() = run { orders = api.orders().items }

    fun loadOrderForm() = run {
        customers = api.customers().items
        orderProducts = api.products(null, null).items
    }

    fun placeOrder(customerId: Int, quantities: Map<Int, Int>, onDone: () -> Unit) = run {
        val items = quantities.filterValues { it > 0 }.map { OrderItemReq(it.key, it.value) }
        val res = api.createOrder(OrderReq(customerId, items))
        message = "Order #${res.id} placed"
        orders = api.orders().items
        onDone()
    }
}
