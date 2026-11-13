package com.example.stockroom

import com.google.gson.Gson
import okhttp3.OkHttpClient
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import java.io.IOException

data class User(val id: Int, val name: String, val email: String, val role: String)
data class LoginReq(val email: String, val password: String)
data class LoginRes(val token: String, val user: User)
data class Page<T>(val items: List<T>, val total: Int)
data class Product(
    val id: Int, val sku: String, val name: String, val category: String?,
    val price: Double, val stock_qty: Int, val reorder_level: Int, val low_stock: Boolean,
)
data class Customer(val id: Int, val name: String, val phone: String?, val email: String?)
data class OrderRow(
    val id: Int, val customer_name: String, val status: String,
    val total: Double, val item_count: Int, val created_at: String,
)
data class Dashboard(
    val products: Int, val units_in_stock: Int, val stock_value: Double, val low_stock_count: Int,
    val sales_today: Double, val sales_month: Double, val orders_today: Int, val customers: Int,
)
data class MoveReq(val product_id: Int, val quantity: Int, val reason: String?)
data class OrderItemReq(val product_id: Int, val quantity: Int)
data class OrderReq(val customer_id: Int, val items: List<OrderItemReq>)
data class OrderRes(val id: Int, val total: Double)
private data class ErrorBody(val error: ErrorInfo?)
private data class ErrorInfo(val message: String?)

interface InventoryApi {
    @POST("api/auth/login") suspend fun login(@Body body: LoginReq): LoginRes
    @POST("api/auth/logout") suspend fun logout(): Map<String, String>
    @GET("api/dashboard") suspend fun dashboard(): Dashboard
    @GET("api/products") suspend fun products(
        @Query("q") q: String?, @Query("low_stock") low: Boolean?, @Query("limit") limit: Int = 200,
    ): Page<Product>
    @POST("api/inventory/stock-in") suspend fun stockIn(@Body body: MoveReq): Product
    @POST("api/inventory/stock-out") suspend fun stockOut(@Body body: MoveReq): Product
    @GET("api/customers") suspend fun customers(@Query("limit") limit: Int = 200): Page<Customer>
    @GET("api/orders") suspend fun orders(@Query("limit") limit: Int = 50): Page<OrderRow>
    @POST("api/orders") suspend fun createOrder(@Body body: OrderReq): OrderRes
}

object ApiClient {
    fun create(token: () -> String?): InventoryApi {
        val http = OkHttpClient.Builder().addInterceptor { chain ->
            val req = chain.request().newBuilder().apply {
                token()?.let { header("Authorization", "Bearer $it") }
            }.build()
            chain.proceed(req)
        }.build()
        return Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE)
            .client(http)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(InventoryApi::class.java)
    }
}

/** Turns network and API failures into a message that can be shown to the user. */
fun Throwable.friendly(): String = when (this) {
    is HttpException -> runCatching {
        Gson().fromJson(response()?.errorBody()?.string(), ErrorBody::class.java)?.error?.message
    }.getOrNull() ?: "Request failed (${code()})"
    is IOException -> "Can't reach the server. Check your connection."
    else -> message ?: "Something went wrong"
}
