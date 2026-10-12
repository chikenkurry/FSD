package repository

import (
	"context"
	"errors"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

var (
	ErrUserNotFound      = errors.New("user not found")
	ErrUsernameDuplicate = errors.New("username already taken")
)

type UserRepository struct {
	db *gorm.DB
}

func NewUserRepository(db *gorm.DB) *UserRepository {
	return &UserRepository{db: db}
}

// Create inserts a new user
func (r *UserRepository) Create(ctx context.Context, user *model.User) error {
	err := r.db.WithContext(ctx).Create(user).Error
	if err != nil {
		if errors.Is(err, gorm.ErrDuplicatedKey) {
			return ErrUsernameDuplicate
		}
		return err
	}
	return nil
}

// GetByID fetches a user by primary key
func (r *UserRepository) GetByID(ctx context.Context, id uuid.UUID) (*model.User, error) {
	var user model.User
	err := r.db.WithContext(ctx).First(&user, "id = ?", id).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}
	return &user, nil
}

// GetByIDWithRelations fetches a user and preloads their created plans and memberships
func (r *UserRepository) GetByIDWithRelations(ctx context.Context, id uuid.UUID) (*model.User, error) {
	var user model.User
	err := r.db.WithContext(ctx).
		Preload("CreatedPlans").
		Preload("Memberships").
		First(&user, "id = ?", id).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrUserNotFound
		}
		return nil, err
	}
	return &user, nil
}

// List fetches users with pagination
func (r *UserRepository) List(ctx context.Context, limit, offset int) ([]model.User, int64, error) {
	var users []model.User
	var total int64

	db := r.db.WithContext(ctx).Model(&model.User{})

	if err := db.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	err := db.Order("username ASC").
		Limit(limit).
		Offset(offset).
		Find(&users).Error

	return users, total, err
}

// Update updates a user's username
func (r *UserRepository) Update(ctx context.Context, user *model.User) error {
	result := r.db.WithContext(ctx).
		Model(user).
		Where("id = ?", user.ID).
		Update("username", user.Username)

	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrUserNotFound
	}
	return nil
}

// Delete removes a user by ID
func (r *UserRepository) Delete(ctx context.Context, id uuid.UUID) error {
	result := r.db.WithContext(ctx).Delete(&model.User{}, "id = ?", id)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrUserNotFound
	}
	return nil
}