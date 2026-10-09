package dev.photohouse.connected

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import dev.photohouse.connected.core.validAssetLookupId

@Composable internal fun AssetLookupDialog(zh: Boolean, dismiss: () -> Unit, open: (String) -> Unit) {
    fun t(en: String, cn: String) = if (zh) cn else en
    var input by remember { mutableStateOf("") }
    val valid = validAssetLookupId(input)
    AlertDialog(onDismissRequest = dismiss,
        title = { Text(t("Open by number", "按编号打开")) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(t("Enter a photo or video number in this library.", "输入此资料库中照片或视频的编号。"))
            OutlinedTextField(input, { if (it.length <= 19 && it.all { c -> c in '0'..'9' }) input = it },
                label = { Text(t("Asset number", "媒体编号")) }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { if (valid) open(input) }),
                isError = input.isNotEmpty() && !valid,
                modifier = Modifier.fillMaxWidth().testTag("asset-lookup-input"))
        } },
        dismissButton = { TextButton(onClick = dismiss) { Text(t("Cancel", "取消")) } },
        confirmButton = { Button(onClick = { if (valid) open(input) }, enabled = valid,
            modifier = Modifier.testTag("asset-lookup-open")) { Text(t("Open", "打开")) } })
}
