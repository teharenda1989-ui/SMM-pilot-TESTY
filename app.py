@app.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    with get_db() as conn:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            start_time = request.form.get('start_time', '10:00')
            end_time = request.form.get('end_time', '22:00')
            interval_minutes = int(request.form.get('interval_minutes', 30))
            days_of_week = request.form.get('days_of_week', 'all')
            days = request.form.get('days', 'Ежедневно')
            
            # Генерируем все времена
            from datetime import datetime, timedelta
            
            start_dt = datetime.strptime(start_time, '%H:%M')
            end_dt = datetime.strptime(end_time, '%H:%M')
            
            times = []
            current = start_dt
            while current <= end_dt:
                times.append(current.strftime('%H:%M'))
                current += timedelta(minutes=interval_minutes)
            
            # Сохраняем каждое время
            for time in times:
                cursor.execute('''
                    INSERT INTO schedule (user_id, time, days, start_time, end_time, interval_minutes, days_of_week)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (session['user_id'], time, days, start_time, end_time, interval_minutes, days_of_week))
            
            conn.commit()
            flash(f'✅ Добавлено {len(times)} времен публикации!', 'success')
            return redirect(url_for('schedule'))
        
        cursor.execute('SELECT * FROM schedule WHERE user_id = ? AND is_active = 1 ORDER BY time', 
                      (session['user_id'],))
        schedule_list = cursor.fetchall()
    
    return render_template('schedule.html', schedule=schedule_list)
