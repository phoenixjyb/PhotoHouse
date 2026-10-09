package dev.photohouse.home

import kotlinx.serialization.json.*
import java.time.LocalDate
import java.time.YearMonth
import java.util.Locale

data class CalendarRequest(val year:Int?=null,val month:Int?=null,val page:Int=1) {
    val level get()=if(month!=null) "day" else if(year!=null) "month" else "year"
    fun valid()=page in 1..1000 && (year==null || year in 1..9999) && (month==null || year!=null && month in 1..12)
    fun parent()=if(month!=null) CalendarRequest(year) else CalendarRequest()
    fun range():Pair<String,String>? = year?.let { y ->
        if(month==null) String.format(Locale.ROOT,"%04d-01-01",y) to String.format(Locale.ROOT,"%04d-12-31",y)
        else YearMonth.of(y,month).let { it.atDay(1).toString() to it.atEndOfMonth().toString() }
    }
}
data class CalendarBucket(val key:String,val from:String,val through:String,val count:Int,val cover:HomeAsset?) {
    fun child()=if(key.length==4) CalendarRequest(key.toInt()) else if(key.length==7) CalendarRequest(key.take(4).toInt(),key.takeLast(2).toInt()) else null
}
data class CalendarPage(val request:CalendarRequest,val total:Int,val hasMore:Boolean,val dated:Int,val undated:Int,val buckets:List<CalendarBucket>)
data class CalendarState(val request:CalendarRequest=CalendarRequest(),val page:CalendarPage?=null,val loading:Boolean=false,val problem:HomeError?=null,val covers:HomeStore?=null)

internal object CalendarWire {
    private fun bad():Nothing=throw HomeFailure(HomeError.INVALID)
    private fun check(v:Boolean) { if(!v) bad() }
    private fun JsonElement.obj(vararg keys:String)=(this as? JsonObject ?: bad()).also { check(it.keys==keys.toSet()) }
    private fun JsonElement.number(low:Int=0,high:Int=Int.MAX_VALUE):Int {
        val p=this as? JsonPrimitive ?: bad();check(!p.isString && p.content.matches(Regex("0|[1-9][0-9]*")))
        return p.content.toIntOrNull()?.takeIf { it in low..high } ?: bad()
    }
    private fun JsonElement.string():String=(this as? JsonPrimitive)?.takeIf { it.isString }?.content ?: bad()
    fun parse(bytes:ByteArray,snapshot:DiscoverySnapshot,request:CalendarRequest):CalendarPage = try {
        check(request.valid())
        val o=HomeWire.parse(bytes).obj("version","revision","catalog_revision","binding","library","level","year","month","page","page_size","total","has_more","dated_assets","undated_assets","items")
        check(o.getValue("version").number()==1 && o.getValue("revision").number()==snapshot.revision && o.getValue("catalog_revision").number()==snapshot.catalogRevision)
        check(snapshot.binding!=null && o.getValue("binding").string()==snapshot.binding)
        val library=o.getValue("library").obj("id","title")
        check(library.getValue("id").string()==snapshot.libraryId && library.getValue("title").string()==snapshot.libraryTitle)
        check(o.getValue("level").string()==request.level && o.getValue("year")==request.year?.let(::JsonPrimitive).orNull() && o.getValue("month")==request.month?.let(::JsonPrimitive).orNull())
        check(o.getValue("page").number()==request.page && o.getValue("page_size").number()==12)
        val total=o.getValue("total").number(0,when(request.level) { "year"->9999;"month"->12;else->31 })
        val more=(o.getValue("has_more") as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull ?: bad()
        check(more==(request.page*12<total))
        val dated=o.getValue("dated_assets").number(0,100000);val undated=o.getValue("undated_assets").number(0,100000)
        val coverage=snapshot.options.coverage[DiscoveryField.DATES] ?: bad()
        check(dated==coverage.withValues && undated==coverage.withoutValues)
        val items=o.getValue("items") as? JsonArray ?: bad();check(items.size==minOf(12,maxOf(0,total-(request.page-1)*12)))
        val buckets=items.map { e ->
            val b=e.obj("key","from_date","through_date","count","cover");val key=b.getValue("key").string()
            check(key.matches(Regex(when(request.level) { "year"->"[0-9]{4}";"month"->"[0-9]{4}-[0-9]{2}";else->"[0-9]{4}-[0-9]{2}-[0-9]{2}" })))
            val y=key.take(4).toInt();check(y in 1..9999 && (request.year==null || request.year==y))
            val m=if(key.length>=7) key.substring(5,7).toInt() else null
            check(request.month==null || request.month==m)
            val range=if(key.length==10) LocalDate.parse(key).toString().let { it to it } else CalendarRequest(y,m).range()!!
            check(b.getValue("from_date").string()==range.first && b.getValue("through_date").string()==range.second)
            val cover=if(b.getValue("cover")==JsonNull) null else {
                val feed=buildJsonObject { put("version",3);put("revision",snapshot.catalogRevision);put("library",library);put("page",1);put("page_size",50);put("total",1);put("has_more",false);put("items",JsonArray(listOf(b.getValue("cover")))) }
                CatalogWire.feed(feed.toString().toByteArray(Charsets.UTF_8),1,snapshot.catalogRevision,version=3).items.single().also { check(it.grid!=null) }
            }
            CalendarBucket(key,range.first,range.second,b.getValue("count").number(1,dated),cover)
        }
        check(buckets.zipWithNext().all { (a,b)->a.key>b.key } && buckets.sumOf { it.count }<=dated)
        val ids=buckets.mapNotNull { it.cover?.id };check(ids.distinct().size==ids.size)
        CalendarPage(request,total,more,dated,undated,buckets)
    } catch(e:HomeFailure) { throw e } catch(_:Exception) { bad() }
    private fun JsonPrimitive?.orNull():JsonElement=this ?: JsonNull
}
