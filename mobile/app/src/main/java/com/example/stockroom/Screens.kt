package com.example.stockroom

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import java.text.NumberFormat

private val currency: NumberFormat = NumberFormat.getCurrencyInstance()
private fun money(v: Double): String = currency.format(v)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StockroomApp(vm: AppViewModel) {
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(vm.message) {
        vm.message?.let { snackbar.showSnackbar(it); vm.message = null }
    }
    var tab by remember { mutableStateOf(0) }
    var newOrder by remember { mutableStateOf(false) }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            if (vm.token != null) {
                TopAppBar(
                    title = { Text(if (newOrder) "New order" else listOf("Dashboard", "Products", "Orders")[tab]) },
                    actions = { TextButton(onClick = { vm.logout() }) { Text("Sign out") } },
                )
            }
        },
        bottomBar = {
            if (vm.token != null && !newOrder) {
                NavigationBar {
                    NavigationBarItem(tab == 0, { tab = 0 }, { Icon(Icons.Default.Home, null) }, label = { Text("Dashboard") })
                    NavigationBarItem(tab == 1, { tab = 1 }, { Icon(Icons.Default.Menu, null) }, label = { Text("Products") })
                    NavigationBarItem(tab == 2, { tab = 2 }, { Icon(Icons.Default.ShoppingCart, null) }, label = { Text("Orders") })
                }
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            when {
                vm.token == null -> LoginScreen(vm)
                newOrder -> NewOrderScreen(vm, onClose = { newOrder = false })
                tab == 0 -> DashboardTab(vm)
                tab == 1 -> ProductsTab(vm)
                else -> OrdersTab(vm, onNewOrder = { newOrder = true })
            }
        }
    }
}

@Composable
fun LoginScreen(vm: AppViewModel) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
        Text("Stockroom", style = MaterialTheme.typography.headlineMedium)
        Text("Sign in to manage stock and orders.", Modifier.padding(bottom = 16.dp))
        OutlinedTextField(
            email, { email = it }, Modifier.fillMaxWidth(), label = { Text("Email") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
        )
        OutlinedTextField(
            password, { password = it }, Modifier.fillMaxWidth().padding(top = 8.dp), label = { Text("Password") },
            singleLine = true, visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
        )
        Button(
            onClick = { vm.login(email, password) },
            Modifier.fillMaxWidth().padding(top = 16.dp),
            enabled = !vm.loading && email.isNotBlank() && password.isNotBlank(),
        ) { Text(if (vm.loading) "Signing in…" else "Sign in") }
    }
}

@Composable
fun DashboardTab(vm: AppViewModel) {
    LaunchedEffect(Unit) { vm.loadDashboard() }
    val d = vm.dashboard
    if (d == null) { Loading(vm.loading); return }
    val stats = listOf(
        "Sales today" to money(d.sales_today), "Sales this month" to money(d.sales_month),
        "Orders today" to d.orders_today.toString(), "Customers" to d.customers.toString(),
        "Products" to d.products.toString(), "Units in stock" to d.units_in_stock.toString(),
        "Stock value" to money(d.stock_value), "Low-stock products" to d.low_stock_count.toString(),
    )
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(stats) { (label, value) ->
            Card(Modifier.fillMaxWidth()) {
                Row(Modifier.padding(16.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(label); Text(value, style = MaterialTheme.typography.titleMedium)
                }
            }
        }
    }
}

@Composable
fun ProductsTab(vm: AppViewModel) {
    var query by remember { mutableStateOf("") }
    var lowOnly by remember { mutableStateOf(false) }
    var moving by remember { mutableStateOf<Pair<Product, Boolean>?>(null) }
    LaunchedEffect(query, lowOnly) { vm.loadProducts(query, lowOnly) }

    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(16.dp)) {
            OutlinedTextField(query, { query = it }, Modifier.fillMaxWidth(), label = { Text("Search name or SKU") }, singleLine = true)
            FilterChip(lowOnly, { lowOnly = !lowOnly }, { Text("Low stock only") }, Modifier.padding(top = 8.dp))
        }
        if (vm.products.isEmpty()) { Loading(vm.loading, "No products match.") }
        LazyColumn(contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(vm.products, key = { it.id }) { p ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(p.name, style = MaterialTheme.typography.titleMedium)
                            Text(money(p.price))
                        }
                        Text("${p.sku} · ${p.category ?: "No category"}", style = MaterialTheme.typography.bodySmall)
                        Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("${p.stock_qty}", Modifier.padding(end = 8.dp))
                            LinearProgressIndicator(
                                progress = { if (p.reorder_level == 0) 1f else (p.stock_qty / (p.reorder_level * 3f)).coerceIn(0f, 1f) },
                                Modifier.weight(1f),
                                color = if (p.low_stock) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                            )
                        }
                        if (p.low_stock) Text("Low stock (reorder at ${p.reorder_level})", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                        if (vm.canManage) {
                            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton({ moving = p to true }) { Text("Stock in") }
                                OutlinedButton({ moving = p to false }) { Text("Stock out") }
                            }
                        }
                    }
                }
            }
        }
    }
    moving?.let { (product, isIn) ->
        StockDialog(product, isIn, onDismiss = { moving = null }) { qty, reason ->
            vm.moveStock(product, qty, reason, isIn, query, lowOnly)
            moving = null
        }
    }
}

@Composable
fun StockDialog(product: Product, isIn: Boolean, onDismiss: () -> Unit, onConfirm: (Int, String) -> Unit) {
    var qty by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }
    val n = qty.toIntOrNull()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (isIn) "Receive stock" else "Remove stock") },
        text = {
            Column {
                Text("${product.name} · ${product.stock_qty} in stock")
                OutlinedTextField(
                    qty, { qty = it.filter(Char::isDigit).take(7) }, Modifier.padding(top = 8.dp),
                    label = { Text("Quantity") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                )
                OutlinedTextField(reason, { reason = it }, Modifier.padding(top = 8.dp), label = { Text("Reason (optional)") }, singleLine = true)
            }
        },
        confirmButton = { TextButton({ onConfirm(n!!, reason) }, enabled = n != null && n > 0) { Text("Save") } },
        dismissButton = { TextButton(onDismiss) { Text("Cancel") } },
    )
}

@Composable
fun OrdersTab(vm: AppViewModel, onNewOrder: () -> Unit) {
    LaunchedEffect(Unit) { vm.loadOrders() }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Button(onNewOrder, Modifier.fillMaxWidth()) { Text("New order") }
        if (vm.orders.isEmpty()) Loading(vm.loading, "No orders yet.")
        LazyColumn(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(vm.orders, key = { it.id }) { o ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("#${o.id} · ${o.customer_name}", style = MaterialTheme.typography.titleMedium)
                            Text(money(o.total))
                        }
                        Text("${o.item_count} items · ${o.status} · ${o.created_at.take(16)} UTC", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}

@Composable
fun NewOrderScreen(vm: AppViewModel, onClose: () -> Unit) {
    LaunchedEffect(Unit) { vm.loadOrderForm() }
    var customer by remember { mutableStateOf<Customer?>(null) }
    var menu by remember { mutableStateOf(false) }
    val qty = remember { mutableStateMapOf<Int, Int>() }
    val total = vm.orderProducts.sumOf { (qty[it.id] ?: 0) * it.price }
    val canSubmit = customer != null && qty.values.any { it > 0 } && !vm.loading

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        CustomerPicker(customer, vm.customers, menu, { menu = it }) { customer = it }
        LazyColumn(Modifier.weight(1f).padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            items(vm.orderProducts, key = { it.id }) { p ->
                val n = qty[p.id] ?: 0
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(p.name); Text("${money(p.price)} · ${p.stock_qty} left", style = MaterialTheme.typography.bodySmall)
                    }
                    TextButton({ if (n > 0) qty[p.id] = n - 1 }, enabled = n > 0) { Text("−") }
                    Text("$n")
                    TextButton({ if (n < p.stock_qty) qty[p.id] = n + 1 }, enabled = n < p.stock_qty) { Text("+") }
                }
            }
        }
        Text("Total ${money(total)}", style = MaterialTheme.typography.titleLarge)
        Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClose, Modifier.weight(1f)) { Text("Cancel") }
            Button({ vm.placeOrder(customer!!.id, qty.toMap(), onClose) }, Modifier.weight(1f), enabled = canSubmit) { Text("Place order") }
        }
    }
}

/** Simple customer picker built from a button and a dropdown menu. */
@Composable
private fun CustomerPicker(selected: Customer?, customers: List<Customer>, open: Boolean, setOpen: (Boolean) -> Unit, onPick: (Customer) -> Unit) {
    androidx.compose.foundation.layout.Box {
        OutlinedButton({ setOpen(true) }, Modifier.fillMaxWidth()) { Text(selected?.name ?: "Choose a customer") }
        DropdownMenu(open, { setOpen(false) }) {
            if (customers.isEmpty()) DropdownMenuItem({ Text("No customers yet. Add one on the web app.") }, { setOpen(false) })
            customers.forEach { c -> DropdownMenuItem({ Text(c.name) }, { onPick(c); setOpen(false) }) }
        }
    }
}

@Composable
private fun Loading(loading: Boolean, emptyText: String = "") {
    Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        if (loading) CircularProgressIndicator() else if (emptyText.isNotEmpty()) Text(emptyText)
    }
}
