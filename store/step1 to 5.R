library(dplyr)
library(tidyr)
library(lubridate)
library(zoo)
library(e1071)
library(keras)

set.seed(42)
tensorflow::set_random_seed(42)  # seeds TF/Keras/NumPy backend too - R's set.seed() alone does NOT reach Keras training

# ------------------------------------------------------------
# STEP 01 — DATA COLLECTION
# ------------------------------------------------------------
cat(strrep("=", 60), "\n")
cat("STEP 01 - DATA COLLECTION\n")
cat(strrep("=", 60), "\n")

RAW_PATH <- "/home/flakesmonamour/Documents/zetechuni/computer_system/Inventory-management/store/raw/retail_store_inventory.csv"   # <-- update path as needed
df_raw <- read.csv(RAW_PATH, stringsAsFactors = FALSE)

cat(sprintf("Loaded dataset: %s rows and %s columns\n", nrow(df_raw), ncol(df_raw)))
cat("Categories:", paste(unique(df_raw$Category), collapse = ", "), "\n")

# Filter to Groceries (perishable goods)
df <- df_raw %>% filter(Category == "Groceries")
cat(sprintf("\nFiltered to 'Groceries': %s rows | %s products | %s stores\n",
            nrow(df), n_distinct(df$Product.ID), n_distinct(df$Store.ID)))

# ------------------------------------------------------------
# STEP 02 — DATA CLEANING
# ------------------------------------------------------------
cat("\n", strrep("=", 60), "\n")
cat("STEP 02 - DATA CLEANING & FEATURE ENGINEERING\n")
cat(strrep("=", 60), "\n")

df$Date <- as.Date(df$Date)
df <- df %>% arrange(Store.ID, Product.ID, Date)

# Null check
null_counts <- colSums(is.na(df))
if (sum(null_counts) == 0) {
  cat("No nulls found - dataset is complete\n")
} else {
  print(null_counts[null_counts > 0])
}

# Forward/back fill per Store-Product group (safeguard)
fill_cols <- c("Inventory.Level", "Units.Sold", "Units.Ordered", "Demand.Forecast")
df <- df %>%
  group_by(Store.ID, Product.ID) %>%
  mutate(across(all_of(fill_cols), ~ na.locf(na.locf(.x, na.rm = FALSE), fromLast = TRUE, na.rm = FALSE))) %>%
  ungroup()
cat("Forward/back fill applied per SKU group\n")

# Outlier capping via IQR
numeric_cols <- c("Inventory.Level", "Units.Sold", "Units.Ordered", "Demand.Forecast")
cat("\nOutlier detection:\n")
for (col in numeric_cols) {
  Q1 <- quantile(df[[col]], 0.25, na.rm = TRUE)
  Q3 <- quantile(df[[col]], 0.75, na.rm = TRUE)
  IQR_val <- Q3 - Q1
  lower <- Q1 - 1.5 * IQR_val
  upper <- Q3 + 1.5 * IQR_val
  n_outliers <- sum(df[[col]] < lower | df[[col]] > upper, na.rm = TRUE)
  df[[col]] <- pmin(pmax(df[[col]], lower), upper)
  cat(sprintf("%-25s: %4d outliers capped to [%.1f, %.1f]\n", col, n_outliers, lower, upper))
}

# ------------------------------------------------------------
# STEP 03 — PREPROCESSING / FEATURE ENGINEERING
# ------------------------------------------------------------

# Encode categoricals
weather_map <- c(Sunny = 0, Cloudy = 1, Rainy = 2, Snowy = 3)
season_map  <- c(Spring = 0, Summer = 1, Autumn = 2, Winter = 3)
df$Weather_Enc <- weather_map[df$Weather.Condition]
df$Season_Enc  <- season_map[df$Seasonality]

region_dummies <- model.matrix(~ Region - 1, data = df) %>% as.data.frame()
names(region_dummies) <- gsub("Region", "Region_", names(region_dummies))
# Regions are East, North, South, West alphabetically - drop East so the
# remaining three (North, South, West) act as the one-hot columns.
region_dummies$Region_East <- NULL
df <- bind_cols(df, region_dummies)

# Calendar features
df$DayOfWeek   <- wday(df$Date, week_start = 1) - 1
df$DayOfMonth  <- day(df$Date)
df$Month       <- month(df$Date)
df$WeekOfYear  <- isoweek(df$Date)
df$IsWeekend   <- as.integer(df$DayOfWeek >= 5)

# Lag features (per Store-Product group)
lag_days <- c(1, 3, 7, 14)
df <- df %>% arrange(Store.ID, Product.ID, Date) %>% group_by(Store.ID, Product.ID)
for (lg in lag_days) {
  df <- df %>%
    mutate(!!paste0("Units_Sold_Lag", lg) := lag(Units.Sold, lg),
           !!paste0("Inventory_Lag", lg)   := lag(Inventory.Level, lg))
}

# Rolling statistics (7d / 14d)
df <- df %>%
  mutate(
    Rolling_Mean_7d  = rollapply(Units.Sold, 7,  mean, align = "right", fill = NA, partial = TRUE),
    Rolling_Std_7d   = rollapply(Units.Sold, 7,  sd,   align = "right", fill = 0,  partial = TRUE),
    Rolling_Mean_14d = rollapply(Units.Sold, 14, mean, align = "right", fill = NA, partial = TRUE)
  ) %>%
  ungroup()
df$Rolling_Std_7d[is.na(df$Rolling_Std_7d)] <- 0

cat("Lag features created  : Units_Sold_Lag1/3/7/14, Inventory_Lag1/3/7/14\n")
cat("Rolling stats created : Rolling_Mean_7d, Rolling_Std_7d, Rolling_Mean_14d\n")

# Drop rows with NA introduced by lag/rolling windows
before_n <- nrow(df)
df <- df %>% drop_na()
cat(sprintf("Dropped %d rows with NA from lag windows, %d rows remain\n", before_n - nrow(df), nrow(df)))

# MinMax scaling
scale_cols <- c("Inventory.Level", "Units.Sold", "Units.Ordered", "Demand.Forecast",
                "Price", "Competitor.Pricing", "Discount",
                "Units_Sold_Lag1", "Units_Sold_Lag3", "Units_Sold_Lag7", "Units_Sold_Lag14",
                "Inventory_Lag1", "Inventory_Lag3", "Inventory_Lag7", "Inventory_Lag14",
                "Rolling_Mean_7d", "Rolling_Std_7d", "Rolling_Mean_14d")

minmax_scale <- function(x) (x - min(x)) / (max(x) - min(x))
scale_params <- lapply(df[scale_cols], function(x) c(min = min(x), max = max(x)))
df_scaled <- df
df_scaled[scale_cols] <- lapply(df[scale_cols], minmax_scale)
cat(sprintf("\nMinMax scaling applied (0-1) to %d numerical features\n", length(scale_cols)))

# Final feature set
region_dummy_cols <- names(region_dummies)[names(region_dummies) != "Region_East"]
feature_cols <- c(
  "Inventory.Level", "Units.Ordered", "Demand.Forecast",
  "Price", "Discount", "Competitor.Pricing",
  "Weather_Enc", "Season_Enc", "Holiday.Promotion",
  region_dummy_cols,
  "DayOfWeek", "DayOfMonth", "Month", "WeekOfYear", "IsWeekend",
  "Units_Sold_Lag1", "Units_Sold_Lag3", "Units_Sold_Lag7", "Units_Sold_Lag14",
  "Inventory_Lag1", "Inventory_Lag3", "Inventory_Lag7", "Inventory_Lag14",
  "Rolling_Mean_7d", "Rolling_Std_7d", "Rolling_Mean_14d"
)
target_col <- "Units.Sold"

# Chronological 80/20 split (no shuffling)
split_idx <- floor(nrow(df_scaled) * 0.8)
df_train <- df_scaled[1:split_idx, ]
df_test  <- df_scaled[(split_idx + 1):nrow(df_scaled), ]
cat(sprintf("\nTrain/Test split (time-ordered): Train %d rows | Test %d rows\n",
            nrow(df_train), nrow(df_test)))

# R's read.csv() turns "Store ID" -> "Store.ID", "Units Sold" -> "Units.Sold", etc.
# Restore the original space-separated names so output columns match the Python pipeline.
restore_spaces <- function(d) {
  names(d) <- gsub("\\.", " ", names(d))
  d
}

write.csv(restore_spaces(df_scaled), "cleaned_grocery_inventory_R.csv", row.names = FALSE)
write.csv(restore_spaces(df_train),  "train_grocery_inventory_R.csv",   row.names = FALSE)
write.csv(restore_spaces(df_test),   "test_grocery_inventory_R.csv",    row.names = FALSE)

# ------------------------------------------------------------
# STEP 04 — MODEL CREATION & TRAINING
# ------------------------------------------------------------

X_train <- as.matrix(df_train[feature_cols])
y_train <- df_train[[target_col]]
X_test  <- as.matrix(df_test[feature_cols])
y_test  <- df_test[[target_col]]

# ---- SVR (e1071) ----
cat("\n", strrep("-", 60), "\n")
cat("SVR MODEL (e1071)\n")
cat(strrep("-", 60), "\n")

# sklearn's default gamma='scale' = 1 / (n_features * X.var()) using population
# variance. e1071's default gamma = 1/ncol(x) is a different value, so it's
# computed explicitly here to give the SVR a sensible, deliberate hyperparameter
# rather than relying on a wrapper default.
X_train_pop_var <- mean((X_train - mean(X_train))^2)
gamma_scale <- 1 / (ncol(X_train) * X_train_pop_var)
cat(sprintf("SVR gamma = %.8f\n", gamma_scale))

svr_model <- svm(
  x = X_train, y = y_train,
  kernel = "radial", cost = 100, epsilon = 0.01, gamma = gamma_scale
)
cat("SVR training complete\n")
saveRDS(svr_model, "svr_model_R.rds")

# ---- LSTM (keras) ----
cat("\n", strrep("-", 60), "\n")
cat("LSTM MODEL (Keras / TensorFlow)\n")
cat(strrep("-", 60), "\n")

SEQ_LEN <- 14
n_features <- length(feature_cols)

make_sequences <- function(X, y, seq_len) {
  n <- nrow(X) - seq_len
  X_seq <- array(0, dim = c(n, seq_len, ncol(X)))
  y_seq <- numeric(n)
  for (i in 1:n) {
    X_seq[i, , ] <- X[i:(i + seq_len - 1), ]
    y_seq[i] <- y[i + seq_len]
  }
  list(X = X_seq, y = y_seq)
}

train_seq <- make_sequences(X_train, y_train, SEQ_LEN)
test_seq  <- make_sequences(X_test,  y_test,  SEQ_LEN)
cat(sprintf("Sequence built - window = %d days\n", SEQ_LEN))
cat(sprintf("LSTM train shape: (%d, %d, %d)\n", dim(train_seq$X)[1], SEQ_LEN, n_features))

lstm_model <- keras_model_sequential(name = "LSTM_StockLevel") %>%
  layer_lstm(units = 64, return_sequences = TRUE, input_shape = c(SEQ_LEN, n_features)) %>%
  layer_dropout(rate = 0.2) %>%
  layer_lstm(units = 32, return_sequences = FALSE) %>%
  layer_dropout(rate = 0.2) %>%
  layer_dense(units = 16, activation = "relu") %>%
  layer_dense(units = 1)

lstm_model %>% compile(optimizer = "adam", loss = "mse", metrics = "mae")
summary(lstm_model)

early_stop  <- callback_early_stopping(monitor = "val_loss", patience = 5, restore_best_weights = TRUE)
checkpoint  <- callback_model_checkpoint("lstm_best_model_R.keras", monitor = "val_loss", save_best_only = TRUE)

cat("\nTraining LSTM (epochs=50, batch=32, early stopping patience=5)\n")
history <- lstm_model %>% fit(
  train_seq$X, train_seq$y,
  epochs = 50,
  batch_size = 32,
  validation_split = 0.15,
  callbacks = list(early_stop, checkpoint),
  verbose = 1
)

# Predictions come entirely from the R-trained model — nothing borrowed
# from the Python pipeline.
lstm_preds <- as.numeric(predict(lstm_model, test_seq$X))

# ------------------------------------------------------------
# STEP 05 — EVALUATION
# ------------------------------------------------------------
cat("\n", strrep("=", 60), "\n")
cat("MODEL VALIDATION\n")
cat(strrep("=", 60), "\n")

smape <- function(actual, predicted) {
  100 * mean(2 * abs(predicted - actual) / (abs(actual) + abs(predicted) + 1e-8))
}
rmse <- function(actual, predicted) sqrt(mean((actual - predicted)^2))

evaluate_model <- function(name, y_true, y_pred) {
  s <- smape(y_true, y_pred)
  r <- rmse(y_true, y_pred)
  acc <- max(0, 100 - s)
  cat(sprintf("\n%s\n  sMAPE    : %.4f%%\n  RMSE     : %.6f\n  Accuracy : %.2f%%\n", name, s, r, acc))
  data.frame(Model = name, sMAPE = round(s, 4), RMSE = round(r, 6), Accuracy = round(acc, 2))
}

svr_preds <- predict(svr_model, X_test[(SEQ_LEN + 1):nrow(X_test), ])

lstm_metrics <- evaluate_model("LSTM", test_seq$y, lstm_preds)
svr_metrics  <- evaluate_model("SVR",  test_seq$y, svr_preds)

metrics_df <- rbind(lstm_metrics, svr_metrics)
write.csv(metrics_df, "validation_metrics_R.csv", row.names = FALSE)

# Save LSTM training history
history_df <- data.frame(
  epoch    = seq_along(history$metrics$loss),
  loss     = history$metrics$loss,
  val_loss = history$metrics$val_loss,
  mae      = history$metrics$mae,
  val_mae  = history$metrics$val_mae
)
write.csv(history_df, "lstm_training_history_R.csv", row.names = FALSE)

# Save validation predictions (aligned with test_seq, offset by SEQ_LEN)
pred_rows <- (SEQ_LEN + 1):nrow(df_test)

# Inventory.Level in df_test is already MinMax-scaled (0-1) from STEP 03
inv_level <- df_test$Inventory.Level[pred_rows]

# Same reorder/expiry-risk rules used throughout the project:
# reorder alert  = predicted demand > 70% of current inventory
# expiry risk    = inventory > 60% AND predicted demand < 30%
reorder_alert <- as.integer(lstm_preds > (inv_level * 0.70))
expiry_risk   <- as.integer((inv_level > 0.60) & (lstm_preds < 0.30))

predictions_df <- data.frame(
  "Date"            = df_test$Date[pred_rows],
  "Store ID"        = df_test$Store.ID[pred_rows],
  "Product ID"      = df_test$Product.ID[pred_rows],
  "Category"        = df_test$Category[pred_rows],
  "Actual"          = test_seq$y,
  "LSTM_Predicted"  = lstm_preds,
  "SVR_Predicted"   = as.numeric(svr_preds),
  "Inventory_Level" = inv_level,
  "Reorder_Alert"   = reorder_alert,
  "Expiry_Risk"     = expiry_risk,
  check.names = FALSE
)
write.csv(predictions_df, "validation_predictions_R.csv", row.names = FALSE)

# ---- Diagnostic: prediction spread + reorder/expiry counts ----
cat("\n", strrep("-", 60), "\n")
cat("DIAGNOSTIC: LSTM PREDICTION SPREAD & EXPIRY RISK\n")
cat(strrep("-", 60), "\n")
cat(sprintf("Actual          : mean=%.4f  sd=%.4f  range=[%.4f, %.4f]\n",
            mean(test_seq$y), sd(test_seq$y), min(test_seq$y), max(test_seq$y)))
cat(sprintf("LSTM_Predicted  : mean=%.4f  sd=%.4f  range=[%.4f, %.4f]\n",
            mean(lstm_preds), sd(lstm_preds), min(lstm_preds), max(lstm_preds)))
cat(sprintf("SVR_Predicted   : mean=%.4f  sd=%.4f  range=[%.4f, %.4f]\n",
            mean(svr_preds), sd(svr_preds), min(svr_preds), max(svr_preds)))
cat(strrep("-", 60), "\n")
cat(sprintf("Rows with Inventory_Level > 0.60 : %d of %d\n", sum(inv_level > 0.60), length(inv_level)))
if (sum(inv_level > 0.60) > 0) {
  cat(sprintf("Min LSTM_Predicted among those    : %.4f\n", min(lstm_preds[inv_level > 0.60])))
}
cat(sprintf("Reorder_Alert rows : %d\n", sum(reorder_alert)))
cat(sprintf("Expiry_Risk rows (inv>0.60 & lstm<0.30) : %d\n", sum(expiry_risk)))
cat(strrep("-", 60), "\n")

cat("\nDone. Outputs saved: svr_model_R.rds, lstm_best_model_R.keras, validation_metrics_R.csv, validation_predictions_R.csv, lstm_training_history_R.csv\n")